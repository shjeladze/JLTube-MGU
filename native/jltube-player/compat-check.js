// SPDX-License-Identifier: GPL-3.0-or-later
'use strict';
const fs = require('fs');
const os = require('os');

function evaluate(input) {
    const errors = [];
    if (input.platform !== 'linux') errors.push('The native player requires Linux');
    if (input.arch !== 'x64' || input.endian !== 'LE') errors.push('This package requires little-endian x86-64; ARM and other architectures are not included');
    const hmi = input.id7 && !input.id8 ? 'ID7' : input.id8 && !input.id7 ? 'ID8' : null;
    if (!hmi) errors.push('Could not identify exactly one supported MGU OAP platform');
    ['python', 'ca', 'renderer', 'unshare'].forEach((name) => {
        if (input[name] !== true) errors.push('Missing prerequisite: ' + name);
    });
    return { schema: 1, hmi: hmi, architecture: input.arch, installable: errors.length === 0,
        errors: errors, realCarValidated: false, audio: 'disabled', browser: 'unavailable' };
}

function detect() {
    return evaluate({platform: process.platform, arch: process.arch, endian: os.endianness(),
        id7: fs.existsSync('/usr/lib/oap-mainapp'), id8: fs.existsSync('/usr/lib/oap-mainapp21'),
        python: fs.existsSync('/var/opt/mgu-python/current/bin/python3'),
        ca: fs.existsSync('/var/opt/mgu-python/current/ssl/cacert.pem'),
        renderer: fs.existsSync('/var/opt/mgu-render/current/mgu-render'),
        unshare: fs.existsSync('/usr/bin/unshare')});
}
exports.evaluate = evaluate;
exports.detect = detect;
if (require.main === module) {
    const report = detect();
    process.stdout.write(JSON.stringify(report) + '\n');
    process.exitCode = report.installable ? 0 : 2;
}
