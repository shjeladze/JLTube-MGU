'use strict';
const assert = require('assert');
const Ui = require('../apps/shjeladze_jltube/src/ui.js').Ui;
const evaluate = require('../native/jltube-player/compat-check.js').evaluate;

async function test() {
    for (const hmi of ['ID7', 'ID8']) {
        const writes = [];
        const rhmi = {getByName: (name) => {
            if (/^jltubeHmi/.test(name)) return name === 'jltubeHmi' + hmi ? {} : null;
            return {setValue: (...args) => { writes.push([name].concat(args)); return Promise.resolve(); }};
        }};
        const ui = new Ui(rhmi);
        await ui.text('results', 'Video title', 3);
        await ui.text('status', 'Locked');
        await ui.text('urlText', 'https://www.youtube.com/');
        assert.deepStrictEqual(writes[0], ['results', 3, hmi === 'ID8' ? 'PrimaryText' : 'Text', 'Video title', 'Text']);
        assert.strictEqual(writes[1][2], 'Text');
        assert.strictEqual(writes[2][2], 'Text');
    }
    assert.throws(() => new Ui({getByName: () => null}), /Unsupported/);
    assert.throws(() => new Ui({getByName: () => ({})}), /Unsupported/);
    const base = {platform: 'linux', arch: 'x64', endian: 'LE', id7: true, id8: false,
                  python: true, ca: true, renderer: true, unshare: true};
    assert.strictEqual(evaluate(base).installable, true);
    assert.strictEqual(evaluate(Object.assign({}, base, {id7: false, id8: true})).hmi, 'ID8');
    for (const change of [{arch: 'arm64'}, {arch: 'ia32'}, {endian: 'BE'}, {platform: 'win32'},
                           {id7: false}, {id8: true}, {python: false}, {ca: false}, {renderer: false}, {unshare: false}]) {
        const report = evaluate(Object.assign({}, base, change));
        assert.strictEqual(report.installable, false);
        assert(report.errors.length > 0);
        assert.strictEqual(report.realCarValidated, false);
    }
    console.log('ID7/ID8 text routing, unknown-HMI refusal and architecture/prerequisite gates passed.');
}
test().catch((err) => { console.error(err); process.exit(1); });
