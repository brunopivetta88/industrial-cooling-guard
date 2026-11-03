import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
from icg.update_check import main


class Response:
    def __init__(self, body):
        self.body = body
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def read(self, limit):
        return self.body[:limit]


class UpdateTests(unittest.TestCase):
    def check(self, body):
        output = io.StringIO()
        with patch.object(sys, 'argv', ['check', '--current', 'v1']), patch('urllib.request.urlopen', return_value=Response(body)), redirect_stdout(output):
            main()
        return json.loads(output.getvalue())

    def test_discovery_without_install(self):
        result = self.check(b'{"tag_name":"v2","draft":false,"prerelease":false}')
        self.assertTrue(result['different_release'])
        self.assertFalse(result['installed'])

    def test_no_change(self):
        self.assertFalse(self.check(b'{"tag_name":"v1"}')['different_release'])

    def test_bad_or_oversized_metadata(self):
        for data in [b'not json', b'x' * 262145, b'{"tag_name":"v2","draft":true}']:
            with self.assertRaises(SystemExit) as exc:
                self.check(data)
            self.assertEqual(exc.exception.code, 1)
