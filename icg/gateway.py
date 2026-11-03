"""Experimental loopback-only Modbus lab gateway. Never deploy inline unreviewed."""
import argparse
import asyncio
import ipaddress
import json
import struct
import time
from .__main__ import Engine, parse_request


async def read_adu(reader):
    header = await asyncio.wait_for(reader.readexactly(7), 3)
    _, protocol, length, _ = struct.unpack('>HHHB', header)
    if protocol or not 2 <= length <= 254:
        raise ValueError('invalid MBAP length/protocol')
    return header + await asyncio.wait_for(reader.readexactly(length - 1), 3)


def exception(request, code=3):
    return request[:4] + struct.pack('>HBBB', 3, request[6], request[7] | 128, code)


def validate_response(request, response):
    if response[:2] != request[:2] or response[6] != request[6]:
        raise ValueError('response transaction/unit mismatch')
    fc = request[7]
    if response[7] == fc | 128:
        if len(response) != 9 or response[8] == 0:
            raise ValueError('invalid exception response')
        return
    if response[7] != fc:
        raise ValueError('response function mismatch')
    if fc in (3, 4):
        count = int.from_bytes(request[10:12], 'big')
        if len(response) != 9 + 2 * count or response[8] != 2 * count:
            raise ValueError('invalid read response')
    elif fc == 6 and response != request:
        raise ValueError('invalid write echo')
    elif fc == 16 and (len(response) != 12 or response[8:12] != request[8:12]):
        raise ValueError('invalid multiple-write response')


class Gateway:
    def __init__(self, config, host, port):
        if not ipaddress.ip_address(host).is_loopback:
            raise ValueError('this gateway is restricted to loopback lab targets')
        if set(config['targets']) != {host}:
            raise ValueError('exactly one matching lab target required')
        if not config['targets'][host].get('temperatures'):
            raise ValueError('commissioned temperature rules required')
        if set(config['targets'][host].get('registers', {})) != set(config['targets'][host]['temperatures']):
            raise ValueError('lab gateway only permits registers with temperature policies')
        self.engine = Engine(config)
        self.host, self.port = host, port
        self.lock = asyncio.Lock()
        self.clients = 0

    async def handle(self, reader, writer):
        self.clients += 1
        upstream = None
        try:
            if self.clients > 8:
                return
            peer = writer.get_extra_info('peername')[0]
            if peer not in self.engine.config['targets'][self.host]['writers']:
                return
            for _ in range(100):
                request = await read_adu(reader)
                async with self.lock:
                    event = dict(timestamp=time.monotonic(), source=peer, target=self.host, adu_hex=request.hex())
                    alerts = self.engine.inspect(event)
                    unit, _, _, values = parse_request(request)
                    if not 1 <= unit <= 247:
                        alerts.append('invalid_unit')
                    print(json.dumps({'event': 'decision', 'alerts': alerts, 'forwarded': not alerts}), flush=True)
                    if alerts:
                        response = exception(request)
                    else:
                        upstream_reader, upstream = await asyncio.wait_for(asyncio.open_connection(self.host, self.port), 3)
                        upstream.write(request)
                        await asyncio.wait_for(upstream.drain(), 3)
                        response = await read_adu(upstream_reader)
                        validate_response(request, response)
                        upstream.close()
                        await upstream.wait_closed()
                        upstream = None
                    writer.write(response)
                    await asyncio.wait_for(writer.drain(), 3)
        except (ValueError, OSError, asyncio.TimeoutError, asyncio.IncompleteReadError):
            # No retry: a timed-out write might already have reached the server.
            print(json.dumps({'event': 'connection_closed', 'reason': 'invalid_frame_or_io_error'}), flush=True)
        finally:
            if upstream is not None:
                upstream.close()
            writer.close()
            self.clients -= 1


async def run(args):
    with open(args.config) as handle:
        gateway = Gateway(json.load(handle), '127.0.0.1', args.target_port)
    server = await asyncio.start_server(gateway.handle, '127.0.0.1', args.listen_port, limit=1024, backlog=8)
    async with server:
        await server.serve_forever()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--listen-port', type=int, default=1502)
    parser.add_argument('--target-port', type=int, default=2502)
    parser.add_argument('--lab-only', action='store_true', required=True)
    args = parser.parse_args()
    if args.listen_port == args.target_port or not all(1024 <= p <= 65535 for p in (args.listen_port, args.target_port)):
        parser.error('use distinct unprivileged ports')
    asyncio.run(run(args))


if __name__ == '__main__':
    main()
