"""Commissioned engineering-unit limits. No vendor register guesses."""
import math


def number(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('expected finite number')
    return value


class TemperatureGuard:
    def __init__(self, config):
        self.rules = {}
        self.state = {}
        for target, policy in config['targets'].items():
            for key, rule in policy.get('temperatures', {}).items():
                unit, address = (int(x) for x in key.split(':'))
                if not 1 <= unit <= 247 or not 0 <= address <= 65535:
                    raise ValueError('invalid temperature register')
                if set(rule) != {'signed', 'scale', 'offset', 'minimum', 'maximum', 'initial', 'max_step', 'max_rise_per_minute'}:
                    raise ValueError('temperature rule has missing or unknown fields')
                if type(rule['signed']) is not bool:
                    raise ValueError('signed must be boolean')
                for name in set(rule) - {'signed'}:
                    number(rule[name])
                if rule['scale'] <= 0 or not rule['minimum'] <= rule['initial'] <= rule['maximum'] or rule['max_step'] <= 0 or rule['max_rise_per_minute'] <= 0:
                    raise ValueError('invalid temperature envelope')
                if key not in policy.get('registers', {}):
                    raise ValueError('temperature register needs a raw register bound')
                self.rules[target, key] = dict(rule)

    def inspect(self, target, unit, address, values, timestamp, commit):
        alerts, updates = [], {}
        for index, raw in enumerate(values):
            key = (target, f'{unit}:{address + index}')
            rule = self.rules.get(key)
            if rule is None:
                continue
            signed = raw - 65536 if rule['signed'] and raw >= 32768 else raw
            value = signed * rule['scale'] + rule['offset']
            previous, last_time, credit = self.state.get(key, (rule['initial'], timestamp, rule['max_step']))
            credit = min(rule['max_step'], credit + max(0, timestamp - last_time) * rule['max_rise_per_minute'] / 60)
            rise = max(0, value - previous)
            if not rule['minimum'] <= value <= rule['maximum']:
                alerts.append('temperature_outside_envelope')
            if abs(value - previous) > rule['max_step'] + 1e-9:
                alerts.append('temperature_step_exceeded')
            if rise > credit + 1e-9:
                alerts.append('temperature_rise_budget_exceeded')
            updates[key] = (value, timestamp, credit - rise)
        # An invalid multi-register transaction cannot seed future baselines.
        if commit and not alerts:
            self.state.update(updates)
        return alerts
