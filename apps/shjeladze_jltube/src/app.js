// SPDX-License-Identifier: GPL-3.0-or-later
'use strict';
const OnlineApp = require('oap-sdk/src/core/OnlineApp.js');
const logging = require('oap-sdk/src/logging/logging');
const fs = require('fs');
const path = require('path');
const request = require('./client.js').request;
const Video = require('./render.js').Video;
const Keyboard = require('./keyboard.js').Keyboard;
const Actions = require('./actions.js').Actions;
const Ui = require('./ui.js').Ui;
const log = logging.getSDKLogger();
class JLTube extends OnlineApp {
    constructor() {
        super(); this.visible = false; this.busy = false; this.dead = false;
        this.allowed = false; this.typing = false; this.keyboard = new Keyboard();
        this.results = []; this.resultKey = '';
        this.gpu = new Video('shjeladze_jltube');
        this.on('initialized', () => this.setup().catch((err) => log.error(err.message)));
        this.on('entryPointExecute', (uuid) => {
            if (this.rhmiApplication) this.rhmiApplication.openEntryState(uuid).catch((err) => log.warn(err.message));
        });
        this.on('changeVisibility', (v) => { if (v && v.visible === false) this.hide(); });
        this.on('shutdown', () => {
            this.dead = true; clearInterval(this.timer); this.hide();
            this.destroyBundles().then(() => process.exit(0)).catch(() => process.exit(1));
        });
        this.on('error', (err) => log.warn(err.message));
    }
    hide() {
        this.visible = false; this.allowed = false; this.typing = false; this.keyboard.clear();
        this.renderKeyboard();
        this.gpu.close(); request({op: 'stop'}).catch(() => {});
        if (this._initialized && this._appStatusService) {
            Promise.resolve(this.unregisterHmiVisible()).catch(() => {});
            Promise.resolve(this.registerInactive()).catch(() => {});
        }
    }
    async setup() {
        const rhmi = this.rhmiApplication;
        if (!rhmi) return this.initialized();
        this.ui = new Ui(rhmi);
        const state = rhmi.getByName('JLTubeHome');
        state.on('focus', (v) => {
            if (v && (v.focus === true || v.focus === 1 || v.focus === 'true')) {
                this.visible = true;
                Promise.resolve(this.registerActive()).catch(() => {});
                Promise.resolve(this.registerHmiVisible()).catch(() => {});
            }
            else this.hide();
        });
        state.on('visible', (event) => { if (!event || event.visible === false || event.visible === 0) this.hide(); });
        rhmi.on('applicationStackChanged', (stack) => {
            if (stack && Object.keys(stack).length && !Object.prototype.hasOwnProperty.call(stack, 'ROOT_APP')) this.hide();
        });
        rhmi.on('restoreHmi', () => { this.gpu.close(); this.updateAvailability(false); request({op: 'stop'}).catch(() => {}); });
        const actions = new Actions();
        const bind = (name, fn) => actions.bind(rhmi.getByName(name), name, fn);
        rhmi.on('userEvent', (event) => actions.raw(event));
        bind('google', () => this.open('web', 'https://www.google.com/'));
        bind('youtube', () => this.beginUrl('search'));
        bind('results', (event) => {
            if (!this.visible || !this.allowed || this.typing) return;
            const entry = this.results[Number(event && event.row)];
            if (entry) this.open('youtube', entry.url);
        });
        bind('enterWeb', () => this.beginUrl('web'));
        bind('enterYouTube', () => this.beginUrl('youtube'));
        bind('letters', (event) => {
            if (!this.allowed || !this.visible || !this.typing) return;
            this.keyboard.append(Number(event && event.row)); this.renderKeyboard();
        });
        bind('nextKeys', () => { if (this.typing && this.allowed) { this.keyboard.next(); this.renderKeyboard(); } });
        bind('erase', () => { if (this.typing && this.allowed) { this.keyboard.backspace(); this.renderKeyboard(); } });
        bind('cancelUrl', () => { this.typing = false; this.keyboard.clear(); this.renderKeyboard(); });
        bind('submitUrl', () => {
            if (!this.typing || !this.allowed || !this.visible) return;
            const url = this.keyboard.value, mode = this.keyboard.mode;
            this.typing = false; this.keyboard.clear(); this.renderKeyboard(); this.open(mode, url);
        });
        bind('custom', () => {
            // Owner-selected URL, never interpreted as code. A native speller remains a validation item.
            try {
                const f = path.join(__dirname, '..', '..', 'data', 'portal.json');
                const config = JSON.parse(fs.readFileSync(f, 'utf8'));
                this.open(config.mode === 'youtube' ? 'youtube' : 'web', config.url);
            } catch (err) { this.text('Add data/portal.json with mode and url; see README.'); }
        });
        bind('stop', () => { this.gpu.show(false); request({op: 'stop'}).catch(() => {}); });
        this.updateAvailability(false);
        const entry = this.getEntryPoints().find((ep) => ep.getDescription().name === 'shjeladze_jltube');
        if (!entry) throw new Error('JLTube entry point unavailable');
        await entry.init();
        await rhmi.mapEntryState(entry.getDescription().uuid, state);
        await entry.setAvailability('ENABLED');
        await this.initialized();
        this.timer = setInterval(() => this.poll(), 500);
        const last = this.getLastExecutedEntryPointUuid && this.getLastExecutedEntryPointUuid();
        if (last) await rhmi.openEntryState(last);
    }
    text(value) {
        if (!this.rhmiApplication || this.dead) return;
        this.ui.text('status', value)
            .then(() => this.rhmiApplication.flush()).catch((err) => log.warn(err.message));
    }
    open(mode, url) {
        if (!this.visible || !this.allowed) return;
        const message = mode === 'search' ? {op: 'search', query: url} : {op: 'open', mode: mode, url: url};
        request(message).then((r) => this.text(r.error || (mode === 'search' ? 'Searching YouTube…' : 'Starting…')))
            .catch((err) => this.text(err.message));
    }
    beginUrl(mode) {
        if (!this.visible || !this.allowed) return;
        this.gpu.show(false); request({op: 'stop'}).catch(() => {});
        this.keyboard.begin(mode); this.typing = true; this.renderKeyboard();
    }
    updateAvailability(allowed) {
        this.allowed = allowed === true;
        if (!this.allowed) { this.typing = false; this.keyboard.clear(); this.results = []; this.resultKey = ''; }
        this.renderKeyboard();
    }
    renderKeyboard() {
        if (!this.rhmiApplication || !this.ui || this.dead) return;
        const rhmi = this.rhmiApplication;
        const pending = [];
        ['google', 'youtube', 'custom', 'enterWeb', 'enterYouTube'].forEach((name) => {
            const comp = rhmi.getByName(name);
            pending.push(Promise.resolve(comp.setProperty('Focusable', this.allowed && !this.typing ? 3 : 0, 'UInt')));
            pending.push(Promise.resolve(comp.setProperty('Visible', this.typing ? 0 : 1, 'UInt')));
        });
        ['urlText', 'letters', 'nextKeys', 'erase', 'submitUrl', 'cancelUrl'].forEach((name) => {
            pending.push(Promise.resolve(rhmi.getByName(name).setProperty('Visible', this.typing && this.allowed ? 1 : 0, 'UInt')));
        });
        pending.push(Promise.resolve(rhmi.getByName('results').setProperty('Visible', this.allowed && !this.typing && this.results.length ? 1 : 0, 'UInt')));
        if (this.typing && this.allowed) {
            pending.push(this.ui.text('urlText', this.keyboard.value));
            const letters = rhmi.getByName('letters'), keys = this.keyboard.keys();
            pending.push(Promise.resolve(letters.setRowCount(keys.length)).then(() => Promise.all(keys.map((key, row) =>
                this.ui.text('letters', key === ' ' ? 'Space' : key, row)))));
        }
        Promise.all(pending).then(() => rhmi.flush()).catch((err) => log.warn(err.message));
    }
    async poll() {
        if (this.busy || !this.visible || this.dead) return;
        this.busy = true;
        try {
            const r = await request({op: 'status'});
            if (!this.visible || this.dead) return;
            if (this.allowed !== (r.allowed === true)) this.updateAvailability(r.allowed === true);
            this.text(r.error || r.reason || r.state || 'Player unavailable — locked');
            const results = Array.isArray(r.results) ? r.results.slice(0, 10) : [];
            const key = JSON.stringify(results);
            if (this.allowed && key !== this.resultKey) {
                this.results = results; this.resultKey = key;
                const component = this.rhmiApplication.getByName('results');
                if (results.length) {
                    Promise.resolve(component.setRowCount(results.length)).then(() => Promise.all(results.map((item, row) =>
                        this.ui.text('results', String(item.title).slice(0, 160), row))))
                        .then(() => this.rhmiApplication.flush()).catch((err) => log.warn(err.message));
                }
                this.renderKeyboard();
            }
            this.gpu.show(!this.typing && r.allowed === true && r.state === 'playing', r.videoGeneration);
        } catch (err) { this.gpu.close(); this.updateAvailability(false); this.text('Player unavailable — locked'); }
        finally { this.busy = false; }
    }
}
new JLTube().start().catch((err) => log.error(err.message));
