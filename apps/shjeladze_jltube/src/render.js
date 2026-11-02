'use strict';
const net = require('net');
function word(n) { const b = Buffer.alloc(4); b.writeUInt32LE(n >>> 0, 0); return b; }
class Video {
    constructor(id) { this.id = id; this.socket = null; this.ready = false; this.shown = false; this.area = null; }
    send(type, payload) {
        if (this.socket && !this.socket.destroyed) this.socket.write(Buffer.concat([word(type), word(payload.length), payload]));
    }
    connect() {
        if (this.socket) return;
        const socket = net.createConnection('/run/mgu-render/render.sock');
        this.socket = socket;
        let pending = Buffer.alloc(0);
        socket.on('connect', () => this.send(1, Buffer.from(this.id + '\0proto=mgu-render/1')));
        socket.on('error', () => this.close());
        socket.on('close', () => { this.ready = false; this.socket = null; this.shown = false; });
        socket.on('data', (data) => {
            pending = Buffer.concat([pending, data]);
            if (pending.length > 65536) return this.close();
            while (pending.length >= 8) {
                const type = pending.readUInt32LE(0), length = pending.readUInt32LE(4);
                if (length > 65528) return this.close();
                if (pending.length < length + 8) return;
                const p = pending.slice(8, 8 + length); pending = pending.slice(8 + length);
                if (type === 0x4d520101 && p.length >= 44) {
                    this.area = [28, 32, 36, 40].map((o) => p.readInt32LE(o));
                    this.ready = !!((p.readUInt32LE(4) & 1) && (p.readUInt32LE(8) & 16) &&
                        this.area[2] > 0 && this.area[3] > 0);
                }
                if (type === 103 || type === 106) this.close();
            }
        });
    }
    show(on, generation) {
        if (!on) { this.send(3, word(0)); this.send(14, word(1)); this.shown = false; return; }
        this.connect();
        if (!this.ready) return;
        if (this.shown && generation !== this.generation) {
            this.send(14, word(1)); this.shown = false;
        }
        if (!this.shown) {
            this.generation = generation;
            this.send(0x4d520001, word(1));
            const place = Buffer.alloc(28);
            this.area.forEach((v, i) => place.writeInt32LE(v, i * 4));
            place.writeFloatLE(1, 16); this.send(2, place);
            this.send(13, Buffer.concat([word(1), Buffer.from('/dev/shm/mgu-video-jltube\0')]));
            this.send(3, word(1)); this.shown = true;
        }
        const frame = Buffer.alloc(36);
        frame.writeUInt32LE(1, 0); frame.writeUInt32LE(0x000000ff, 4);
        frame.writeUInt32LE(19, 8);
        [0, 0, this.area[2], this.area[3], 0].forEach((v, i) => frame.writeFloatLE(v, 12 + i * 4));
        frame.writeUInt32LE(1, 32); this.send(7, frame);
    }
    close() {
        if (this.socket) { const s = this.socket; this.socket = null; s.destroy(); }
        this.ready = false; this.shown = false;
    }
}
exports.Video = Video;

