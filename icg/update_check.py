"""Check for a release; never execute downloaded content or alter policies."""
import argparse
import json
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--current', required=True, help='Currently approved release tag')
    args = parser.parse_args()
    request = urllib.request.Request('https://api.github.com/repos/brunopivetta88/industrial-cooling-guard/releases/latest', headers={'Accept': 'application/vnd.github+json', 'User-Agent': 'industrial-cooling-guard-update-check'})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = response.read(262145)
            if len(body) > 262144:
                raise ValueError('oversized release metadata')
            release = json.loads(body)
        if not isinstance(release, dict) or not isinstance(release.get('tag_name'), str) or release.get('draft') or release.get('prerelease'):
            raise ValueError('invalid stable release metadata')
        print(json.dumps({'event': 'update_check', 'different_release': release['tag_name'] != args.current, 'current': args.current, 'latest': release['tag_name'], 'review_url': 'https://github.com/brunopivetta88/industrial-cooling-guard/releases', 'installed': False}))
    except (OSError, ValueError) as exc:
        print(json.dumps({'event': 'update_check_failed', 'reason': str(exc), 'installed': False}))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
