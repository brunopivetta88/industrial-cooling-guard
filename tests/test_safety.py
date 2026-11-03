import asyncio
import copy
import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from icg.__main__ import Engine
from icg.gateway import Gateway, read_adu, validate_response
from icg.capture import Streams


def config():
    return json.loads(Path('examples/temperature-lab.json').read_text())


def event(value=-200, timestamp=1):
    return dict(timestamp=timestamp, source='127.0.0.1', target='127.0.0.1', adu_hex='00010000000601060064' + (value & 65535).to_bytes(2, 'big').hex())


class TemperatureTests(unittest.TestCase):
    def test_signed_normal(self):
        self.assertEqual(Engine(config()).inspect(event(-195)), [])

    def test_extreme_rise(self):
        self.assertIn('temperature_outside_envelope', Engine(config()).inspect(event(1000)))

    def test_extreme_drop(self):
        self.assertIn('temperature_outside_envelope', Engine(config()).inspect(event(-1000)))

    def test_large_step_inside_envelope(self):
        self.assertIn('temperature_step_exceeded', Engine(config()).inspect(event(-160)))

    def test_small_steps_cannot_bypass_budget(self):
        engine = Engine(config())
        self.assertEqual(engine.inspect(event(-195, 1)), [])
        self.assertEqual(engine.inspect(event(-190, 2)), [])
        self.assertIn('temperature_rise_budget_exceeded', engine.inspect(event(-185, 3)))

    def test_budget_refill(self):
        engine = Engine(config())
        self.assertEqual(engine.inspect(event(-190, 1)), [])
        self.assertEqual(engine.inspect(event(-185, 61)), [])

    def test_rejected_write_does_not_poison_baseline(self):
        engine = Engine(config())
        engine.inspect(event(1000, 1))
        self.assertEqual(engine.inspect(event(-200, 2)), [])

    def test_unauthorized_write_does_not_poison_baseline(self):
        engine = Engine(config())
        bad = event(-190)
        bad['source'] = 'attacker'
        engine.inspect(bad)
        self.assertEqual(engine.inspect(event(-200, 2)), [])

    def test_non_numeric_timestamp(self):
        bad = event()
        bad['timestamp'] = '1'
        with self.assertRaises(ValueError):
            Engine(config()).inspect(bad)

    def test_bad_rules(self):
        for field, value in [('scale', 0), ('initial', 100), ('maximum', float('nan')), ('signed', 'yes'), ('max_step', -1)]:
            cfg = config()
            cfg['targets']['127.0.0.1']['temperatures']['1:100'][field] = value
            with self.assertRaises(ValueError):
                Engine(cfg)

    def test_broadcast_rejected(self):
        bad = event()
        bad['adu_hex'] = bad['adu_hex'][:12] + '00' + bad['adu_hex'][14:]
        self.assertIn('invalid_write_unit', Engine(config()).inspect(bad))

    def test_bad_config_shape(self):
        for cfg in [[], None, {'targets': {'x': []}}, {'targets': {'x': {'writers': [], 'registers': []}}}]:
            with self.assertRaises(ValueError):
                Engine(cfg)


class StreamTests(unittest.TestCase):
    def setUp(self):
        self.streams = Streams(['127.0.0.1'])
        self.raw = event()['adu_hex']

    def row(self, sequence=1, data='', syn='0', stream='0'):
        return ['1', '127.0.0.2', '127.0.0.1', '502', stream, str(sequence), syn, '0', '0', data]

    def test_requires_syn(self):
        self.assertEqual(self.streams.feed(self.row(data=self.raw)), [])

    def test_split_and_coalesced(self):
        self.streams.feed(self.row(sequence=0, syn='1'))
        self.assertEqual(self.streams.feed(self.row(data=self.raw[:10])), [])
        result = self.streams.feed(self.row(sequence=6, data=self.raw[10:] + self.raw))
        self.assertEqual([e['adu_hex'] for e in result], [self.raw, self.raw])

    def test_duplicate_retransmission(self):
        self.streams.feed(self.row(sequence=0, syn='1'))
        self.assertEqual(len(self.streams.feed(self.row(data=self.raw))), 1)
        self.assertEqual(self.streams.feed(self.row(data=self.raw)), [])

    def test_gap_drops_stream(self):
        self.streams.feed(self.row(sequence=0, syn='1'))
        with self.assertRaises(ValueError):
            self.streams.feed(self.row(sequence=4, data=self.raw))
        self.assertEqual(self.streams.feed(self.row(data=self.raw)), [])

    def test_flow_limit(self):
        self.streams.max_flows = 1
        self.streams.feed(self.row(sequence=0, syn='1'))
        with self.assertRaises(ValueError):
            self.streams.feed(self.row(sequence=0, syn='1', stream='2'))


class Writer:
    def __init__(self):
        self.data = b''
    def get_extra_info(self, name):
        return ('127.0.0.1', 9999)
    def write(self, data):
        self.data += data
    async def drain(self):
        pass
    def close(self):
        pass
    async def wait_closed(self):
        pass


class GatewayTests(unittest.IsolatedAsyncioTestCase):
    async def test_bad_temperature_never_reaches_upstream(self):
        reader, writer = asyncio.StreamReader(), Writer()
        reader.feed_data(bytes.fromhex(event(1000)['adu_hex']))
        reader.feed_eof()
        with patch('asyncio.open_connection', new_callable=AsyncMock) as connect:
            await Gateway(config(), '127.0.0.1', 2502).handle(reader, writer)
            connect.assert_not_awaited()
        self.assertEqual(writer.data[7:9], b'\x86\x03')

    async def test_safe_temperature_forwarded_once(self):
        raw = bytes.fromhex(event(-195)['adu_hex'])
        reader, writer, upstream_reader, upstream_writer = asyncio.StreamReader(), Writer(), asyncio.StreamReader(), Writer()
        reader.feed_data(raw)
        reader.feed_eof()
        upstream_reader.feed_data(raw)
        with patch('asyncio.open_connection', new_callable=AsyncMock, return_value=(upstream_reader, upstream_writer)) as connect:
            await Gateway(config(), '127.0.0.1', 2502).handle(reader, writer)
            connect.assert_awaited_once()
        self.assertEqual(upstream_writer.data, raw)
        self.assertEqual(writer.data, raw)

    async def test_invalid_length(self):
        reader = asyncio.StreamReader()
        reader.feed_data(bytes.fromhex('00010000ffff01'))
        with self.assertRaises(ValueError):
            await read_adu(reader)

    async def test_mismatched_response(self):
        request = bytes.fromhex(event()['adu_hex'])
        with self.assertRaises(ValueError):
            validate_response(request, b'\x00\x02' + request[2:])

    async def test_remote_target_disabled(self):
        with self.assertRaises(ValueError):
            Gateway(config(), '192.0.2.20', 502)
