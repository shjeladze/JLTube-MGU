// SPDX-License-Identifier: GPL-3.0-or-later
'use strict';
// ID7 firmware can report both component actions and raw RHMI ACTION events.
class Actions {
    constructor(clock) {
        this.clock = clock || (() => { const t = process.hrtime(); return t[0] * 1000 + t[1] / 1e6; });
        this.entries = {}; this.last = {};
    }
    bind(component, name, handler) {
        const entry = { name: name, handler: handler };
        try { this.entries[Number(component.getId())] = entry; } catch (err) { /* component events still work */ }
        component.on('action', (event) => this.press(entry, event && event.row));
    }
    press(entry, value) {
        const row = value === undefined || value === null ? 0 : Number(value);
        if (!Number.isInteger(row) || row < 0 || row > 255) return;
        const key = entry.name + '.' + row, now = this.clock();
        if (this.last[key] !== undefined && now - this.last[key] < 120) return;
        this.last[key] = now;
        entry.handler({ row: row });
    }
    raw(event) {
        if (!event || event.eventType !== 'ACTION') return;
        const entry = this.entries[Number(event.sourceId)];
        if (!entry) return;
        const map = event.parameterMap || {};
        this.press(entry, typeof map.get === 'function' ? map.get(2) : map[2]);
    }
}
exports.Actions = Actions;
