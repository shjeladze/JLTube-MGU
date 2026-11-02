#!/usr/bin/env python3
"""Run the read-only preflight over explicitly named SSH. Does not install anything."""
import argparse
import json
from pathlib import Path
import re
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('--host', required=True)
parser.add_argument('--user', default='root')
parser.add_argument('--port', type=int, default=22)
parser.add_argument('--identity')
parser.add_argument('--out', default='target-report.json')
args = parser.parse_args()
if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.:-]{0,252}', args.host) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]*', args.user):
    parser.error('Invalid SSH host or user')
if not 1 <= args.port <= 65535:
    parser.error('Invalid SSH port')
source = (Path(__file__).resolve().parents[1] / 'native/jltube-player/preflight.py').read_text(encoding='utf8')
argv = ['ssh', '-T', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes', '-o', 'ConnectTimeout=5', '-p', str(args.port)]
if args.identity:
    argv += ['-i', args.identity]
argv += [args.user + '@' + args.host, '/var/opt/mgu-python/current/bin/python3 -']
result = subprocess.run(argv, input=source, capture_output=True, text=True, timeout=30)
if result.returncode:
    raise SystemExit('Read-only preflight could not run. Check the verified SSH host key, supplied identity and mgu-python installation. No installation was attempted.')
try:
    report = json.loads(result.stdout)
    if report.get('schema') != 1 or report.get('readOnly') is not True:
        raise ValueError('Unexpected target report')
except ValueError:
    raise SystemExit('Target returned an invalid report; no output report was saved.')
Path(args.out).write_text(json.dumps(report, sort_keys=True, indent=2) + '\n', encoding='utf8')
print('Saved read-only compatibility report to', args.out)
