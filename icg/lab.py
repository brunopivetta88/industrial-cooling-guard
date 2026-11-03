"""Local-only synthetic Modbus server, not an equipment model."""
import asyncio
import struct
from .gateway import read_adu, exception
from .__main__ import parse_request


async def handle(reader, writer):
    try:
        request = await read_adu(reader)
        unit, fc, address, values = parse_request(request)
        if values:
            response = request if fc == 6 else request[:4] + struct.pack('>H', 6) + request[6:12]
        elif fc in (3, 4):
            count = int.from_bytes(request[10:12], 'big')
            response = request[:4] + struct.pack('>HBBB', 3 + count * 2, unit, fc, count * 2) + struct.pack('>H', 65336) * count
        else:
            response = exception(request, 1)
        writer.write(response)
        await writer.drain()
    except (ValueError, OSError, asyncio.IncompleteReadError, asyncio.TimeoutError):
        pass
    finally:
        writer.close()


async def main():
    server = await asyncio.start_server(handle, '127.0.0.1', 2502, limit=1024)
    print('Synthetic lab server on 127.0.0.1:2502; no physical equipment connected', flush=True)
    async with server:
        await server.serve_forever()


if __name__ == '__main__':
    asyncio.run(main())
