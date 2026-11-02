#!/usr/bin/env python3
"""Request one allowlisted inventory operation through existing verified SSH."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import threading

OPERATIONS = ('summary', 'platform', 'graphics', 'browser', 'audio', 'network', 'safety', 'report')
LIMIT = 128 * 1024


def ssh_argv(host, operation, user='root', port=22, identity=None):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,252}', host):
        raise ValueError('Use an SSH hostname, IPv4 address or configured SSH alias')
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]{0,31}', user) or not 1 <= port <= 65535:
        raise ValueError('Invalid SSH user or port')
    if operation not in OPERATIONS:
        raise ValueError('Unsupported operation')
    argv = ['ssh', '-T', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
            '-o', 'ClearAllForwardings=yes', '-o', 'ForwardAgent=no', '-o', 'ForwardX11=no',
            '-o', 'ConnectTimeout=5', '-o', 'ServerAliveInterval=5', '-o', 'ServerAliveCountMax=2',
            '-p', str(port)]
    if identity:
        argv += ['-i', str(Path(identity).resolve())]
    argv += [user + '@' + host,
             '/var/opt/mgu-python/current/bin/python3 /var/opt/mgu-inspector/current/inspector.py ' + operation]
    return argv


def request(argv):
    # The SSH command is fixed apart from an allowlisted operation; never shell=True.
    proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    data = []
    def read():
        data.append(proc.stdout.read(LIMIT + 1))
        if len(data[0]) > LIMIT:
            proc.kill()
    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    try:
        proc.wait(timeout=25)
        reader.join(timeout=2)
        if reader.is_alive() or proc.returncode or not data or len(data[0]) > LIMIT:
            raise ValueError('Inventory request failed or exceeded its limit')
        report = json.loads(data[0])
        if (not isinstance(report, dict) or report.get('schema') != 1
                or report.get('tool') != 'mgu-inspector' or report.get('readOnly') is not True):
            raise ValueError('Unexpected inventory response')
        return report
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=3)
        proc.stdout.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True)
    parser.add_argument('--operation', choices=OPERATIONS, default='report')
    parser.add_argument('--user', default='root')
    parser.add_argument('--port', type=int, default=22)
    parser.add_argument('--identity')
    parser.add_argument('--out', default='mgu-inspector-report.json')
    args = parser.parse_args()
    try:
        result = request(ssh_argv(args.host, args.operation, args.user, args.port, args.identity))
        if result.get('operation') != args.operation:
            raise ValueError('Response operation mismatch')
        Path(args.out).write_text(json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    except (OSError, ValueError, subprocess.TimeoutExpired):
        parser.exit(2, 'Could not collect inventory. Check the installed tool, verified SSH host key and existing access. No installation or SSH setup was attempted.\n')
    print('Read-only inventory saved to ' + args.out)


if __name__ == '__main__':
    main()
