"""One-shot paired report for local automation. Pairing code is never an argv item."""
import argparse
import getpass
import json
from pathlib import Path
import sys
from inspector_pair_client import Connection, OPERATIONS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True, help='MGU Tailscale IPv4 address')
    parser.add_argument('--operation', choices=OPERATIONS, default='report')
    parser.add_argument('--out', default='mgu-report.json')
    parser.add_argument('--code-stdin', action='store_true', help='Read one code line from stdin instead of a hidden prompt')
    args = parser.parse_args()
    c = None
    try:
        code = sys.stdin.readline(128).strip() if args.code_stdin else getpass.getpass('Code shown in the car: ')
        c = Connection(args.host); c.pair(code)
        report = c.collect(args.operation)
        Path(args.out).write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    except Exception:
        parser.exit(2, 'Pairing/report failed. Check the private Tailscale peer, car app, fresh code and service. No SSH is used.\n')
    finally:
        if c and c.token:
            try: c.revoke()
            except Exception: pass  # Absolute session expiry remains enforced on the unit.
    print('Read-only report saved to ' + args.out)


if __name__ == '__main__': main()
