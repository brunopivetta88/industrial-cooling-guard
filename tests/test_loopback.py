"""Actual TCP integration, skipped only if the runtime prohibits local binding."""
import asyncio
import json
import unittest
from pathlib import Path
from icg.gateway import Gateway, read_adu
from icg.lab import handle


class LoopbackIntegration(unittest.IsolatedAsyncioTestCase):
    async def test_fragmented_safe_write_and_rejected_extreme_write(self):
        try:
            upstream = await asyncio.start_server(handle, '127.0.0.1', 0)
        except PermissionError:
            self.skipTest('runtime prohibits listening sockets')
        server = None
        writer = None
        try:
            cfg = json.loads(Path('examples/temperature-lab.json').read_text())
            gateway = Gateway(cfg, '127.0.0.1', upstream.sockets[0].getsockname()[1])
            server = await asyncio.start_server(gateway.handle, '127.0.0.1', 0)
            reader, writer = await asyncio.open_connection('127.0.0.1', server.sockets[0].getsockname()[1])
            safe = bytes.fromhex('00010000000601060064ff3d')
            writer.write(safe[:5])
            await writer.drain()
            writer.write(safe[5:])
            await writer.drain()
            self.assertEqual(await read_adu(reader), safe)
            writer.write(bytes.fromhex('0002000000060106006403e8'))
            await writer.drain()
            response = await read_adu(reader)
            self.assertEqual(response[7:], bytes([134, 3]))
        finally:
            if writer:
                writer.close()
                await writer.wait_closed()
            if server:
                server.close()
                await server.wait_closed()
            upstream.close()
            await upstream.wait_closed()
