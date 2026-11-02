// SPDX-License-Identifier: GPL-3.0-or-later
'use strict';
const CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._~:/?#[]@!$&'()*+,;=%";
class Keyboard {
    constructor() { this.clear(); }
    clear() { this.value = 'https://'; this.page = 0; this.mode = 'web'; }
    begin(mode) {
        this.clear(); this.mode = mode === 'search' ? 'search' : mode === 'youtube' ? 'youtube' : 'web';
        if (this.mode === 'search') this.value = '';
    }
    characters() { return CHARS + (this.mode === 'search' ? ' ' : ''); }
    keys() { return this.characters().slice(this.page * 12, (this.page + 1) * 12).split(''); }
    next() { this.page = (this.page + 1) % Math.ceil(this.characters().length / 12); }
    append(index) {
        if (!Number.isInteger(index) || index < 0 || index >= this.keys().length || this.value.length >= (this.mode === 'search' ? 256 : 2048)) return;
        this.value += this.keys()[index];
    }
    backspace() { if (this.value.length) this.value = this.value.slice(0, -1); }
    text(text) {
        const forbidden = this.mode === 'search' ? /[\x00-\x1f\x7f]/ : /[\x00-\x20\x7f]/;
        if (typeof text !== 'string' || text.length > (this.mode === 'search' ? 256 : 2048) || forbidden.test(text)) throw new Error('Invalid URL text');
        this.value = text;
    }
}
exports.Keyboard = Keyboard;
