import argparse
import json
import math
import struct
import sys
from collections import deque


def parse_request(raw):
    """Parse one complete Modbus/TCP request ADU, never a TCP segment."""
    if not 8 <= len(raw) <= 260:
        raise ValueError('invalid ADU size')
    _, protocol, length, unit = struct.unpack('>HHHB', raw[:7])
    if protocol != 0 or length != len(raw) - 6:
        raise ValueError('invalid MBAP header')
    fc = raw[7]
    if fc not in (3, 4, 6, 16):
        raise ValueError('unsupported function')
    if fc in (3, 4, 6):
        if len(raw) != 12:
            raise ValueError('invalid request size')
        address, value = struct.unpack('>HH', raw[8:12])
        if fc != 6:
            if not 1 <= value <= 125 or address + value > 65536:
                raise ValueError('invalid read range')
            return unit, fc, address, []
        return unit, fc, address, [value]
    if len(raw) < 13:
        raise ValueError('truncated multiple write')
    address, count, size = struct.unpack('>HHB', raw[8:13])
    if not 1 <= count <= 123 or size != count * 2 or len(raw) != 13 + size or address + count > 65536:
        raise ValueError('invalid multiple write')
    return unit, fc, address, list(struct.unpack('>' + 'H' * count, raw[13:]))


class Engine:
    def __init__(self, config):
        self.config = config
        self.recent = deque()
        self.last_time = -math.inf
        if not isinstance(config.get('targets'), dict) or not config['targets']:
            raise ValueError('targets must be a nonempty object')
        self.window = float(config.get('window_seconds', 10))
        self.limit = config.get('max_writes', 10)
        if not math.isfinite(self.window) or self.window <= 0 or type(self.limit) is not int or not 1 <= self.limit <= 10000:
            raise ValueError('invalid rate policy')
        for policy in config['targets'].values():
            if not isinstance(policy.get('writers'), list) or not all(isinstance(s, str) for s in policy['writers']):
                raise ValueError('writers must be a list of source identifiers')
            for bounds in policy.get('registers', {}).values():
                if len(bounds) != 2 or not all(type(v) is int for v in bounds) or not 0 <= bounds[0] <= bounds[1] <= 65535:
                    raise ValueError('invalid register bounds')

    def inspect(self, event):
        timestamp = float(event['timestamp'])
        if not math.isfinite(timestamp) or timestamp < self.last_time:
            raise ValueError('events require finite, chronological timestamps')
        self.last_time = timestamp
        source, target = event['source'], event['target']
        if not isinstance(source, str) or not isinstance(target, str):
            raise ValueError('source and target must be strings')
        policy = self.config['targets'].get(target)
        if policy is None:
            return []
        try:
            unit, fc, address, values = parse_request(bytes.fromhex(event['adu_hex']))
        except (ValueError, TypeError):
            return ['invalid_or_unsupported_request']
        if not values:
            return []
        alerts = []
        if source not in policy['writers']:
            alerts.append('unauthorized_writer')
        while self.recent and self.recent[0][0] <= timestamp - self.window:
            self.recent.popleft()
        # Global bounded history: conservative aggregate write burst per sensor.
        self.recent.append((timestamp,))
        if len(self.recent) > self.limit:
            alerts.append('write_burst')
            self.recent.popleft()
        for offset, value in enumerate(values):
            key = str(unit) + ':' + str(address + offset)
            bounds = policy.get('registers', {}).get(key)
            if bounds is None:
                alerts.append('unmapped_register')
            elif not bounds[0] <= value <= bounds[1]:
                alerts.append('register_out_of_range')
        return sorted(set(alerts))


def main():
    parser = argparse.ArgumentParser(description='Analyze complete request ADUs; never sends control traffic.')
    parser.add_argument('--config', required=True)
    parser.add_argument('--events', required=True, help='JSONL file or - for stdin')
    args = parser.parse_args()
    try:
        with open(args.config) as handle:
            engine = Engine(json.load(handle))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        parser.error(str(exc))
    handle = sys.stdin if args.events == '-' else open(args.events)
    try:
        for number, line in enumerate(handle, 1):
            if len(line) > 8192:
                print(json.dumps({'line': number, 'alerts': ['input_too_large']}), flush=True)
                continue
            try:
                event = json.loads(line)
                alerts = engine.inspect(event)
            except (ValueError, TypeError, KeyError, AttributeError):
                print(json.dumps({'line': number, 'alerts': ['invalid_input']}), flush=True)
                continue
            if alerts:
                print(json.dumps({'line': number, 'timestamp': event['timestamp'], 'source': event['source'], 'target': event['target'], 'alerts': alerts}), flush=True)
    finally:
        if handle is not sys.stdin:
            handle.close()


if __name__ == '__main__':
    main()
