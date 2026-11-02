'use strict';
const OnlineApp = require('oap-sdk/src/core/OnlineApp.js');
const logging = require('oap-sdk/src/logging/logging');
const request = require('./client.js').request;
const Actions = require('./actions.js').Actions;
const log = logging.getSDKLogger();
class Inspector extends OnlineApp {
    constructor() {
        super(); this.dead = false; this.busy = false; this.code = null; this.codeUntil = 0;
        this.on('initialized', () => this.setup().catch((e) => log.error(e.message)));
        this.on('entryPointExecute', (uuid) => {
            if (this.rhmiApplication) this.rhmiApplication.openEntryState(uuid).catch((e) => log.warn(e.message));
        });
        this.on('shutdown', () => {
            this.dead = true; clearInterval(this.timer); this.code = null;
            this.destroyBundles().then(() => process.exit(0)).catch(() => process.exit(1));
        });
        this.on('error', () => log.warn('Inspector platform error'));
    }
    text(name, value) {
        if (this.dead || !this.rhmiApplication) return Promise.resolve();
        const c = this.rhmiApplication.getByName(name);
        if (!c) return Promise.reject(new Error('Inspector UI missing'));
        return Promise.resolve(c.setValue(0, 'Text', value, 'Text'));
    }
    async setup() {
        const rhmi = this.rhmiApplication;
        if (!rhmi) return this.initialized();
        const id7 = !!rhmi.getByName('inspectorHmiID7'), id8 = !!rhmi.getByName('inspectorHmiID8');
        if (id7 === id8) throw new Error('Unknown Inspector HMI');
        const state = rhmi.getByName('InspectorHome'), actions = new Actions();
        state.on('focus', (v) => {
            if (v && (v.focus === true || v.focus === 1 || v.focus === 'true')) {
                Promise.resolve(this.registerActive()).catch(() => {});
                Promise.resolve(this.registerHmiVisible()).catch(() => {});
            } else {
                Promise.resolve(this.unregisterHmiVisible()).catch(() => {});
                Promise.resolve(this.registerInactive()).catch(() => {});
            }
        });
        rhmi.on('userEvent', (e) => actions.raw(e));
        actions.bind(rhmi.getByName('pair'), 'pair', () => this.begin());
        actions.bind(rhmi.getByName('revoke'), 'revoke', () => this.revoke());
        const entry = this.getEntryPoints().find((ep) => ep.getDescription().name === 'shjeladze_inspector');
        if (!entry) throw new Error('Inspector entry unavailable');
        await entry.init(); await rhmi.mapEntryState(entry.getDescription().uuid, state);
        await entry.setAvailability('ENABLED'); await this.initialized();
        this.timer = setInterval(() => this.poll(), 1500);
        const last = this.getLastExecutedEntryPointUuid && this.getLastExecutedEntryPointUuid();
        if (last) await rhmi.openEntryState(last);
        this.poll();
    }
    async begin() {
        if (this.busy || this.dead) return;
        this.busy = true;
        try {
            const r = await request({op: 'begin'});
            if (r.error || !/^[0-9]{12}$/.test(r.code)) throw new Error('Pairing unavailable');
            this.code = r.code; this.codeUntil = Date.now() + 120000;
            await this.text('code', 'Pairing code: ' + this.code.match(/.{4}/g).join(' '));
            await this.text('status', 'Enter this code in the laptop client within 2 minutes.');
            await this.rhmiApplication.flush();
        } catch (e) { await this.text('status', 'Inspector service unavailable; check Store pending restart.'); }
        finally { this.busy = false; }
    }
    async revoke() {
        this.code = null;
        try { await request({op: 'revoke'}); }
        catch (e) { /* Service loss already invalidates all sessions. */ }
        await this.text('code', 'No active pairing code');
        await this.text('status', 'Disconnected. Create a new code to connect again.');
        await this.rhmiApplication.flush();
    }
    async poll() {
        if (this.dead || this.busy) return;
        this.busy = true;
        try {
            const r = await request({op: 'status'});
            if (r.error) throw new Error('Unavailable');
            if (r.connected || !r.pairingActive || Date.now() >= this.codeUntil) {
                this.code = null;
                await this.text('code', 'No active pairing code');
            }
            await this.text('status', r.connected ? 'Laptop connected: read-only session, ' + r.sessionSeconds + ' seconds left.' :
                r.pairingActive ? 'Waiting for the laptop. Private Tailscale connection required.' : 'Ready. Select Create pairing code.');
            await this.rhmiApplication.flush();
        } catch (e) {
            this.code = null;
            await this.text('code', 'No active pairing code');
            await this.text('status', 'Inspector service or app registration unavailable.');
            await this.rhmiApplication.flush();
        } finally { this.busy = false; }
    }
}
new Inspector().start().catch(() => log.error('Inspector startup failed'));
