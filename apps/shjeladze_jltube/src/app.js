// SPDX-License-Identifier: GPL-3.0-or-later
'use strict';
const OnlineApp = require('oap-sdk/src/core/OnlineApp.js');
const logging = require('oap-sdk/src/logging/logging');
const fs = require('fs');
const path = require('path');
const request = require('./client.js').request;
const Video = require('./render.js').Video;
const log = logging.getSDKLogger();
class JLTube extends OnlineApp {
    constructor() {
        super(); this.visible = false; this.busy = false; this.dead = false;
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
        this.visible = false; this.gpu.close(); request({op: 'stop'}).catch(() => {});
        if (this._initialized && this._appStatusService) {
            Promise.resolve(this.unregisterHmiVisible()).catch(() => {});
            Promise.resolve(this.registerInactive()).catch(() => {});
        }
    }
    async setup() {
        const rhmi = this.rhmiApplication;
        if (!rhmi) return this.initialized();
        const state = rhmi.getByName('JLTubeHome');
        state.on('focus', (v) => {
            if (v && (v.focus === true || v.focus === 1 || v.focus === 'true')) {
                this.visible = true;
                Promise.resolve(this.registerActive()).catch(() => {});
                Promise.resolve(this.registerHmiVisible()).catch(() => {});
            }
            else this.hide();
        });
        const bind = (name, fn) => rhmi.getByName(name).on('action', () => fn());
        bind('google', () => this.open('web', 'https://www.google.com/'));
        bind('youtube', () => this.open('web', 'https://www.youtube.com/'));
        bind('custom', () => {
            // Owner-selected URL, never interpreted as code. A native speller remains a validation item.
            try {
                const f = path.join(__dirname, '..', '..', 'data', 'portal.json');
                const config = JSON.parse(fs.readFileSync(f, 'utf8'));
                this.open(config.mode === 'youtube' ? 'youtube' : 'web', config.url);
            } catch (err) { this.text('Add data/portal.json with mode and url; see README.'); }
        });
        bind('stop', () => { this.gpu.show(false); request({op: 'stop'}).catch(() => {}); });
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
        Promise.resolve(this.rhmiApplication.getByName('status').setValue(0, 'Text', value, 'Text'))
            .then(() => this.rhmiApplication.flush()).catch((err) => log.warn(err.message));
    }
    open(mode, url) {
        if (!this.visible) return;
        request({op: 'open', mode: mode, url: url}).then((r) => this.text(r.error || 'Starting…'))
            .catch((err) => this.text(err.message));
    }
    async poll() {
        if (this.busy || !this.visible || this.dead) return;
        this.busy = true;
        try {
            const r = await request({op: 'status'});
            if (!this.visible || this.dead) return;
            this.text(r.error || r.reason || r.state || 'Player unavailable — locked');
            this.gpu.show(r.allowed === true && r.state === 'playing');
        } catch (err) { this.gpu.close(); this.text('Player unavailable — locked'); }
        finally { this.busy = false; }
    }
}
new JLTube().start().catch((err) => log.error(err.message));
