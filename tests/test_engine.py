import json
import struct
import unittest
from pathlib import Path
from icg.__main__ import Engine, parse_request


class DetectionTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads(Path('examples/config.json').read_text())
        self.engine = Engine(self.config)
        self.event = dict(timestamp=1, source='192.0.2.10', target='192.0.2.20', adu_hex='00010000000601060064004b')

    def test_legitimate(self):
        self.assertEqual(self.engine.inspect(self.event), [])

    def test_unknown_writer(self):
        self.event['source'] = '192.0.2.99'
        self.assertIn('unauthorized_writer', self.engine.inspect(self.event))

    def test_out_of_range(self):
        self.event['adu_hex'] = '0001000000060106006403e8'
        self.assertIn('register_out_of_range', self.engine.inspect(self.event))

    def test_burst_and_expiry(self):
        for _ in range(10):
            self.assertNotIn('write_burst', self.engine.inspect(self.event))
        self.assertIn('write_burst', self.engine.inspect(self.event))
        self.event['timestamp'] = 12
        self.assertEqual(self.engine.inspect(self.event), [])

    def test_truncation(self):
        raw = bytes.fromhex(self.event['adu_hex'])
        for i in range(len(raw)):
            with self.assertRaises(ValueError):
                parse_request(raw[:i])

    def test_multiple_write_checks_every_register(self):
        self.event['adu_hex'] = '00010000000b01100064000204004b004b'
        self.assertIn('unmapped_register', self.engine.inspect(self.event))

    def test_bad_byte_count(self):
        with self.assertRaises(ValueError):
            parse_request(bytes.fromhex('00010000000b01100064000202004b004b'))

    def test_read(self):
        self.event['adu_hex'] = '000100000006010300640001'
        self.assertEqual(self.engine.inspect(self.event), [])

    def test_unmonitored_target(self):
        self.event['target'] = '192.0.2.30'
        self.assertEqual(self.engine.inspect(self.event), [])

    def test_invalid_time(self):
        self.event['timestamp'] = float('nan')
        with self.assertRaises(ValueError):
            self.engine.inspect(self.event)

    def test_state_bounded(self):
        for i in range(1000):
            self.event['timestamp'] = i / 1000
            self.engine.inspect(self.event)
        self.assertLessEqual(len(self.engine.recent), 10)

    def test_random_bytes_do_not_crash(self):
        import random
        rng = random.Random(42)
        for _ in range(500):
            raw = rng.randbytes(rng.randrange(300))
            try:
                parse_request(raw)
            except ValueError:
                pass
