# Portable media build

`python3 native/runtime/build.py` runs on Linux, not on the car. It downloads the hash-pinned Zig toolchain, fetches and verifies exact Git object IDs for FFmpeg, QuickJS and OpenSSL, builds native candidates for baseline x86-64 Linux with static musl, and fetches the hash-pinned official yt-dlp zipimport executable. Runtime version/hash metadata is generated from the resulting bytes. No browser engine, BMW SDK or hardware-dependent audio backend is included.

The GitHub workflow **Build portable media package** packages the result into a development Catalog and retains binaries, notices and corresponding library source archives as an Actions artifact. It does not publish a stable release or enable the vehicle bridge. The compiled FFmpeg intentionally supports only the required H.264-over-HTTPS/MP4-to-I420 path; unavailable YouTube formats fail rather than downloading an arbitrary codec/runtime.

Checks include no ELF interpreter dependency for native binaries, QuickJS BigInt, yt-dlp startup, and decoding a one-second offline H.264 fixture to a complete 640x360 I420 frame. HTTPS code is linked with OpenSSL 3.5.9 and the player requires certificate verification. The target's CA bundle, clock, kernel/network behavior, Python/EJS runtime, audio focus and vehicle interfaces still require target validation. Successful compilation is not a claim of universal MGU compatibility.

Files generated under `dist/runtime/`:

* `yt-dlp`, `qjs`, `ffmpeg`, `runtime-lock.json`, `LICENSES.txt`;
* `sources.lock.json` with exact source/toolchain pins;
* `sources/` archives for the FFmpeg, OpenSSL and QuickJS versions used.

To create a Catalog locally after building:

```sh
python3 tools/package.py --runtime-dir dist/runtime --out dist/catalog-media
```

Redistribute corresponding sources/notices alongside the runtime-containing package. Keep source archives off the vehicle and out of the Git repository tree; publish them as release/artifact assets instead.
