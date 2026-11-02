'use strict';
const net = require('net');
exports.request = function (message) {
    return new Promise((resolve, reject) => {
        const socket = net.createConnection('/run/jltube-player/control.sock');
        let input = Buffer.alloc(0), done = false;
        const finish = (err, value) => {
            if (done) return;
            done = true; socket.destroy();
            if (err) reject(err); else resolve(value);
        };
        socket.setTimeout(1500, () => finish(new Error('Player timeout')));
        socket.on('connect', () => socket.write(JSON.stringify(message) + '\n'));
        socket.on('error', (err) => finish(err));
        socket.on('end', () => { if (!done) finish(new Error('Player disconnected')); });
        socket.on('data', (chunk) => {
            input = Buffer.concat([input, chunk]);
            if (input.length > 16384) return finish(new Error('Oversized player reply'));
            const end = input.indexOf(10);
            if (end >= 0) {
                try { finish(null, JSON.parse(input.slice(0, end).toString('utf8'))); }
                catch (err) { finish(err); }
            }
        });
    });
};

