"""Passive tshark adapter: export request ADUs from SYN-observed TCP streams."""
import argparse
import json
import subprocess
import sys
from .__main__ import Engine


class Streams:
    def __init__(self, targets, port=502, max_flows=256):
        self.targets, self.port = set(targets), port
        self.max_flows = max_flows
        self.flows = {}

    def feed(self, row):
        timestamp, source, target, dstport, stream, sequence, syn, fin, reset, hexdata = row
        if target not in self.targets or int(dstport) != self.port:
            return []
        now, sequence = float(timestamp), int(sequence)
        key = (source, target, stream)
        # Evict idle states, and never resume a dropped stream without a SYN.
        self.flows = {k: v for k, v in self.flows.items() if now - v['time'] < 60}
        if syn == '1':
            if len(self.flows) >= self.max_flows and key not in self.flows:
                raise ValueError('flow capacity reached')
            self.flows[key] = dict(seq=sequence + 1, buffer=b'', time=now)
        flow = self.flows.get(key)
        if flow is None:
            return []
        flow['time'] = now
        if reset == '1':
            self.flows.pop(key, None)
            return []
        payload = bytes.fromhex(hexdata.replace(':', ''))
        if payload:
            if syn == '1':
                sequence += 1
            overlap = flow['seq'] - sequence
            if overlap < 0:
                self.flows.pop(key, None)
                raise ValueError('TCP gap/out-of-order; coverage lost until next SYN')
            payload = payload[overlap:]
            flow['seq'] += len(payload)
            flow['buffer'] += payload
            if len(flow['buffer']) > 65536:
                self.flows.pop(key, None)
                raise ValueError('stream buffer exceeded')
        events = []
        while len(flow['buffer']) >= 7:
            data = flow['buffer']
            length = int.from_bytes(data[4:6], 'big')
            if data[2:4] != b'\0\0' or not 2 <= length <= 254:
                self.flows.pop(key, None)
                raise ValueError('invalid MBAP; stream discarded')
            size = 6 + length
            if len(data) < size:
                break
            events.append(dict(timestamp=now, source=source, target=target, adu_hex=data[:size].hex()))
            flow['buffer'] = data[size:]
        if fin == '1':
            self.flows.pop(key, None)
        return events


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--interface')
    mode.add_argument('--pcap')
    parser.add_argument('--port', type=int, default=502)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('invalid port')
    with open(args.config) as handle:
        config = json.load(handle)
    Engine(config)  # Validate the same policy used by the downstream analyzer.
    streams = Streams(config['targets'], args.port)
    fields = ['frame.time_epoch', 'ip.src', 'ip.dst', 'tcp.dstport', 'tcp.stream', 'tcp.seq', 'tcp.flags.syn', 'tcp.flags.fin', 'tcp.flags.reset', 'tcp.payload']
    command = ['tshark', '-n', '-l', '-T', 'fields', '-E', 'separator=/t', '-E', 'occurrence=f']
    command += ['-r', args.pcap] if args.pcap else ['-i', args.interface, '-f', f'tcp port {args.port}']
    command += ['-Y', f'ip && tcp.dstport == {args.port}']
    for field in fields:
        command += ['-e', field]
    print(json.dumps({'event': 'capture_start', 'coverage': 'IPv4, SYN-observed in-order TCP only; stderr health must be monitored'}), file=sys.stderr, flush=True)
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, text=True)
    except FileNotFoundError:
        parser.error('Install tshark from your OS package repository or wireshark.org')
    try:
        while True:
            line = process.stdout.readline(262145)
            if not line:
                break
            if len(line) > 262144:
                raise ValueError('oversized capture row')
            try:
                row = line.rstrip('\n').split('\t')
                if len(row) != 10:
                    raise ValueError('unexpected tshark output')
                for event in streams.feed(row):
                    print(json.dumps(event), flush=True)
            except ValueError as exc:
                print(json.dumps({'event': 'capture_gap', 'reason': str(exc)}), file=sys.stderr, flush=True)
        code = process.wait()
        if code:
            raise SystemExit(code)
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == '__main__':
    main()
