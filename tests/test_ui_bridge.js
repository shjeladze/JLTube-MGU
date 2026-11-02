'use strict';
const assert = require('assert');
const Keyboard = require('../apps/shjeladze_jltube/src/keyboard.js').Keyboard;
const State = require('../native/jltube-player/vehicle_bridge.js').State;
const Actions = require('../apps/shjeladze_jltube/src/actions.js').Actions;
const EventEmitter = require('events');

let pressTime = 0;
const actions = new Actions(() => pressTime), component = new EventEmitter(), presses = [];
component.getId = () => 31;
actions.bind(component, 'letters', (event) => presses.push(event.row));
component.emit('action', { row: 2 });
actions.raw({eventType: 'ACTION', sourceId: 31, parameterMap: {2: 2}});
assert.deepStrictEqual(presses, [2]); // same physical press, two SDK event paths
pressTime += 150;
actions.raw({eventType: 'ACTION', sourceId: 31, parameterMap: new Map([[2, 2]])});
assert.deepStrictEqual(presses, [2, 2]); // intentional repeated character still works
actions.raw({eventType: 'ACTION', sourceId: 999, parameterMap: {2: 1}});
actions.raw({eventType: 'ACTION', sourceId: 31, parameterMap: {2: -1}});
assert.deepStrictEqual(presses, [2, 2]);

const keyboard = new Keyboard();
keyboard.begin('youtube');
assert.strictEqual(keyboard.mode, 'youtube');
const seen = new Set();
do { keyboard.keys().forEach((key) => seen.add(key)); keyboard.next(); } while (keyboard.page !== 0);
assert(seen.has('/') && seen.has('?') && seen.has('=') && seen.has('A') && seen.has('9'));
keyboard.append(0); assert.strictEqual(keyboard.value, 'https://a');
keyboard.backspace(); assert.strictEqual(keyboard.value, 'https://');
keyboard.text('x'.repeat(2048)); keyboard.append(0); assert.strictEqual(keyboard.value.length, 2048);
assert.throws(() => keyboard.text('https://example.com/\n'), /Invalid/);
keyboard.clear(); assert.strictEqual(keyboard.value, 'https://');
keyboard.begin('search'); keyboard.text('live music');
assert.strictEqual(keyboard.value, 'live music');
assert.throws(() => keyboard.text('x'.repeat(257)), /Invalid/);
keyboard.clear();

let now = 10;
const state = new State(() => now);
assert.strictEqual(state.snapshot().valid, false);
state.availability('speed', true); state.availability('selector', true);
state.receive('speed', {speedVehicleCentreOfGravity: 0});
state.receive('selector', {statusActualStageDrive: 'P'});
assert.strictEqual(state.snapshot().valid, true);
assert.strictEqual(state.snapshot().gear, 'P');
now += 0.5; assert.strictEqual(state.snapshot().valid, false);
state.receive('speed', {speedVehicleCentreOfGravity: 640});
assert.strictEqual(state.snapshot().valid, false); // new speed cannot refresh stale selector
state.receive('selector', {statusActualStageDrive: 3});
assert.strictEqual(state.snapshot().gear, 'N');
assert(state.snapshot().speed_mps > 0);
state.receive('selector', {statusActualGearDrive: 'N_OR_P'});
assert.strictEqual(state.snapshot().valid, false); // no guessed selector or N/P shortcut
state.receive('selector', {statusActualStageDrive: 1});
for (const value of [null, false, '0', 65535, -1, NaN, Infinity]) {
    state.receive('speed', {speedVehicleCentreOfGravity: value});
    assert.strictEqual(state.snapshot().valid, false);
}
state.receive('speed', {speedVehicleCentreOfGravity: 0});
state.availability('speed', false); state.availability('speed', true);
assert.strictEqual(state.snapshot().valid, false);
state.receive('speed', {speedVehicleCentreOfGravity: 0});
assert.strictEqual(state.snapshot().valid, true);
const epoch = state.epoch.speed;
state.availability('speed', false); state.availability('speed', true);
assert.notStrictEqual(state.epoch.speed, epoch); // delayed pre-reconnect getter is rejected
state.receive('speed', {speedVehicleCentreOfGravity: 0});
state.receive('selector', {statusActualStageDrive: '__proto__'});
assert.strictEqual(state.snapshot().valid, false);
console.log('URL keyboard and native vehicle-state merge checks passed. No BMW SDK or car accessed.');
