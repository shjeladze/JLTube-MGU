// SPDX-License-Identifier: GPL-3.0-or-later
'use strict';
// Root-owned optional read-only adapter. No SDK, BMW definitions or demo data is shipped.
const fs = require('fs');
const path = require('path');
const SPEED = 'de.bmw.infotainment.vehicle.Vehicle2';
const SELECTOR = 'de.bmw.infrastructure.VehicleInformation';
const FIELDS = { speed: 'statusCarSpeed2', selector: 'statusGearboxDrive' };
const mono = () => { const t = process.hrtime(); return t[0] + t[1] / 1e9; };

class State {
    constructor(clock) { this.clock = clock || mono; this.reset(); }
    reset() { this.speed = null; this.selector = null; this.available = { speed: false, selector: false }; this.epoch = { speed: 0, selector: 0 }; }
    availability(kind, on) {
        this.available[kind] = on === true;
        this.epoch[kind]++;
        this[kind] = null; // availability transitions never reuse pre-transition measurements
    }
    receive(kind, value) {
        if (!this.available[kind]) return;
        const v = value && (kind === 'speed' ? value.speedVehicleCentreOfGravity : value.statusActualStageDrive);
        let decoded = null;
        if (kind === 'speed' && typeof v === 'number' && Number.isInteger(v) && v >= 0 && v < 65535) decoded = v / 64 / 3.6;
        if (kind === 'selector') {
            if (v === 'P' || v === 1) decoded = 'P';
            if (v === 'R' || v === 2) decoded = 'R';
            if (v === 'N' || v === 3) decoded = 'N';
            if (v === 'D' || v === 4) decoded = 'D';
        }
        this[kind] = decoded === null ? null : { value: decoded, at: this.clock() };
    }
    snapshot() {
        const now = this.clock();
        const age = this.speed && this.selector ? Math.max(now - this.speed.at, now - this.selector.at) : null;
        const valid = this.available.speed && this.available.selector && age !== null && age >= 0 && age <= 0.4;
        return { schema: 1, valid: !!valid, age_seconds: valid ? age : null,
            speed_mps: valid ? this.speed.value : null, gear: valid ? this.selector.value : null };
    }
}

async function main(configFile) {
    const cfg = JSON.parse(fs.readFileSync(configFile, 'utf8'));
    // Getter freshness semantics and field validity must be verified from the local firmware.
    if (cfg.confirmed_remote_getters !== true) throw new Error('Remote getter semantics have not been validated');
    const someip = require('someip');
    const state = new State();
    const proxies = [];
    let stopped = false, timer;
    const write = (nonce) => {
        // Only a response to a new broker challenge may carry an authorizing sample.
        if (!nonce || stopped) return;
        const sample = state.snapshot(); sample.nonce = nonce;
        if (!process.stdout.write(JSON.stringify(sample) + '\n')) stop();
    };
    const stop = () => {
        if (stopped) return;
        stopped = true; clearInterval(timer); state.reset();
        process.stdout.write(JSON.stringify(state.snapshot()) + '\n');
        Promise.all(proxies.map((p) => Promise.resolve().then(() => p.shutdown && p.shutdown()).catch(() => {})))
            .then(() => process.exit(0));
        setTimeout(() => process.exit(1), 500);
    };
    process.on('SIGTERM', stop); process.on('SIGINT', stop);
    process.stdout.on('error', stop);
    let input = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', (chunk) => {
        input += chunk;
        if (input.length > 1024) return stop();
        let end;
        while ((end = input.indexOf('\n')) >= 0) {
            const line = input.slice(0, end); input = input.slice(end + 1);
            try {
                const challenge = JSON.parse(line);
                if (!challenge || !/^[a-f0-9]{32}$/.test(challenge.nonce)) return stop();
                write(challenge.nonce);
            } catch (err) { stop(); }
        }
    });
    process.stdin.on('end', stop);
    // Serialize native build/init calls on fresh ticks, as required by the head unit binding.
    const tick = (fn) => new Promise((resolve, reject) => setImmediate(() => {
        try { Promise.resolve(fn()).then(resolve, reject); } catch (err) { reject(err); }
    }));
    for (const spec of [['speed', SPEED], ['selector', SELECTOR]]) {
        const kind = spec[0], iface = spec[1], field = FIELDS[kind];
        const file = path.join(path.dirname(configFile), 'someipInterfaces', iface.replace(/\./g, '_') + '.json');
        const definition = JSON.parse(fs.readFileSync(file, 'utf8'));
        if (!definition.fields || !definition.fields[field] || !definition.fields[field].getter)
            throw new Error('Required read-only getter unavailable: ' + field);
        const proxy = await tick(() => someip.buildProxy(definition, '1').then((p) => p.init().then(() => p)));
        proxies.push(proxy);
        if (!proxy.subscribeToAvailability) throw new Error('Availability subscription is required');
        await tick(() => proxy.subscribeToAvailability((on) => {
            state.availability(kind, on === true); write();
        }));
        if (proxy.isAvailable && proxy.isAvailable() === true) state.availability(kind, true);
        // Events invalidate immediately. Only a new explicit getter response can authorize Park.
        await tick(() => proxy.subscribe({name: field, onReceive: (value) => {
            state.epoch[kind]++; state[kind] = null; write();
        }}));
        let inflight = false, generation = 0;
        const poll = async () => {
            if (inflight || stopped || !state.available[kind]) return;
            inflight = true;
            const sequence = ++generation;
            const epoch = state.epoch[kind];
            const started = mono();
            try {
                const value = await proxy.getValue(field, 250);
                // A delayed response must never be re-labelled as a current measurement.
                if (sequence === generation && epoch === state.epoch[kind] && mono() - started <= 0.25) state.receive(kind, value);
                else state[kind] = null;
            } catch (err) { state[kind] = null; }
            finally { inflight = false; write(); }
        };
        proxy._jlPoll = poll;
    }
    timer = setInterval(() => { proxies.forEach((p) => p._jlPoll()); write(); }, 100);
    write();
}

module.exports = { State };
if (require.main === module) main(process.argv[2]).catch(() => {
    process.stdout.write('{"schema":1,"valid":false}\n');
    // Do not print generated definitions or raw vehicle data.
    process.stderr.write('JLTube vehicle bridge unavailable; playback remains locked\n');
    process.exit(1);
});
