#!/usr/bin/env python3
"""Offline checks; no car connection, network calls or installation."""
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
commands = [[sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'],
            [sys.executable, 'tools/package.py', '--check'], ['node', 'tests/test_ui_bridge.js']]
commands += [['node', '--check', str(p)] for p in sorted((root / 'apps').rglob('*.js'))]
commands += [['node', '--check', 'native/jltube-player/vehicle_bridge.js']]
for command in commands:
    result = subprocess.run(command, cwd=root, timeout=60)
    if result.returncode:
        raise SystemExit(result.returncode)
print('Offline checks passed. Skipped Linux-only checks (if any) still need Linux CI. No car functionality is certified.')
