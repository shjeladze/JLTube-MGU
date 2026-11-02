// SPDX-License-Identifier: GPL-3.0-or-later
'use strict';
// ID8 media-entry buttons use PrimaryText; labels/title retain Text.
const LABELS = ['title', 'status', 'urlText', 'jltubeHmiID7', 'jltubeHmiID8'];
class Ui {
    constructor(rhmi) {
        this.rhmi = rhmi;
        const id8 = !!rhmi.getByName('jltubeHmiID8'), id7 = !!rhmi.getByName('jltubeHmiID7');
        this.hmi = id7 !== id8 ? (id8 ? 'ID8' : 'ID7') : null;
        if (!this.hmi) throw new Error('Unsupported JLTube HMI description');
    }
    cell(name) { return this.hmi === 'ID8' && LABELS.indexOf(name) < 0 ? 'PrimaryText' : 'Text'; }
    text(name, value, row) {
        const component = this.rhmi.getByName(name);
        if (!component) return Promise.reject(new Error('Missing UI component: ' + name));
        return Promise.resolve(component.setValue(row || 0, this.cell(name), value, 'Text'));
    }
}
exports.Ui = Ui;
