# JLTube-MGU

Parked-only YouTube player and web portal project for compatible BMW iDrive 7 and iDrive 8 MGU OAP environments.
**0.4.0 is a development implementation, not a validated in-car player.**
No BMW SDK, car keys, VIN, firmware, prebuilt OAP donor bundle, or media binaries are shipped.

See [ID7/ID8 compatibility](docs/COMPATIBILITY.md) for platform gates. This is not a universal installer for every BMW; audio and a full browser remain unimplemented.

## What works in this implementation

* Lightweight dual-layout ID7/ID8 OAP source package (`mgu-app.json`), linked by the Store against the car's own SDK.
* Separate `jltube-player` tool: local Unix-socket safety broker, pinned-runtime checks, YouTube resolver/FFmpeg process pipeline, and current mgu-render MGVF/I420 triple-buffer output.
* Parked-only policy enforced in the broker, not by a checkbox in the UI. Unknown, stale, invalid, future, nonzero speed, or anything other than gear `P` locks playback. The app cannot send vehicle-state updates or an unlock command.
* App focus/visibility stop, server-side app-heartbeat timeout, child-process cleanup, black-frame output on stop, bounded resolver output and request sizes, HTTPS-only URLs, exact YouTube hosts, TLS verification, no shell evaluation, no automatic dependency downloads.
* Offline tests and reproducible Catalog packages with actual sizes, SHA-256 checksums and per-file tool hashes.
* An in-app URL keyboard that closes/clears when parked-state authorization is lost. Separate website and YouTube-link modes; Stop stays available.
* An optional root-owned native SOME/IP reader with independent speed/selector expiry, availability-generation checks and challenge/response freshness over private pipes. It stays disabled until its firmware-specific getter semantics are verified.
* A read-only compatibility-report collector over explicitly named, verified SSH; no VIN, keys or tokens are read.
* Native **Search YouTube**, ten selectable video results and direct playback requests, independent of a general browser. Search and selection use the same parked-only broker. Live YouTube access remains subject to network/extractor restrictions and target validation.

## Deliberately unresolved

**This is not ready to install for everyday use.** No real car, BMW SDK donor, emulator or live YouTube playback was available. The preceding 0.3.1 Linux build passed static media linking, QuickJS/yt-dlp startup and an actual offline H.264-to-I420 decoder fixture; that does not establish head-unit compatibility.

| Area | Current status |
| --- | --- |
| Vehicle safety adapter | Optional read-only native bridge implemented; disabled and untested on MGU. Requires the unit's local binding/definitions and proof of fresh remote getter semantics. Default locked. See [bridge validation](docs/VEHICLE_BRIDGE.md). |
| YouTube | Native search, result selection and resolver/decoder pipeline implemented; portable runtime build is automated. Real-MGU playback and audio remain unvalidated. |
| Google/general URLs | Portal buttons and URL validation exist. **Full browser engine is not implemented or bundled.** Web requests return a clear unavailable message. |
| URL entry | RHMI character-list keyboard and optional saved `data/portal.json` implemented; actual controller/touch, focus and lockout behavior need HMI validation. |
| Audio | Explicitly disabled (`-an`). BMW media-session ownership, audio focus, PCM routing, mixer format, resampling, suspend and mute behavior remain unknown. |
| Renderer | Protocol encoded from the pinned upstream specification; real renderer, foreground gating, sizing, cached-frame clearing and HMI lifecycle need integration tests. |
| System service | Layout and permissions checked statically. systemd 237, unshare/mount availability, resource limits, UID allocation, recmgr startup/restart and Python libraries need target verification. |

The absence of a browser backend must not be mistaken for successful Google/YouTube web navigation. A screenshot renderer or an HTTP client would not provide a full browser. Do not disable Chromium's sandbox to make an incompatible build start. Validate engine ABI, glibc/kernel requirements, GPU/software rendering, sandbox support, memory/CPU, fonts, TLS, input/keyboard, redirects/downloads, DRM and process shutdown before adding browser support. Its entire process tree and display output must obey the same parked-only broker.

## Architecture and permissions

`ID7 OAP UI → /run/jltube-player/control.sock → safety broker → unprivileged media workers → /dev/shm/mgu-video-jltube → mgu-render`

The OAP process connects to `/run/mgu-render/render.sock` as its own app UID; the renderer uses that UID for foreground gating. Native programs never run inside the OAP package. The broker is root only for local credential checks, trusted state reads, privilege dropping and a root-owned frame file (accepted by the renderer). yt-dlp, QuickJS and FFmpeg run as UID/GID **3921**, with no supplementary groups, under `NoNewPrivileges`. No interactive account or sudo is created. `prepare` refuses an existing account/process at that UID; also inspect other installed tools for reserved but inactive UID collisions before installation.

The control socket is `root:tm_oap_app`, mode `0660`; the broker additionally checks Linux `SO_PEERCRED` against the installed app UID discovered from the root deploy registry (or an explicit root configuration). No TCP/HTTP server, remote control page, password/token store or root-command endpoint is exposed. Do not add the broker to broad privileged groups. Tools are installed by the Store's deploy tool, never by app JavaScript.

The service runs in a private mount namespace and binds its own resolver file over `/etc/resolv.conf` there, failing startup if binding fails. The head unit's resolver and network defaults stay unchanged. The updater installs mgu-uplink first; the tool's `internet: true, uids: [3921]` authorizes only that worker UID through uplink. The app also declares `internet: true`/`mguInternet: true`. DNS comes from `/run/mgu-uplink/lease.json`. The media workers need DNS plus outbound HTTPS to YouTube and `*.googlevideo.com`; yt-dlp can need other YouTube-owned challenge/API endpoints. Allow certificate validation and a correct system clock. No inbound network access is required. The stock car-network routes still exist under uplink; this build does not provide a general browser network sandbox or DNS-rebinding defense. Such isolation is a prerequisite for a future general browser.

## Offline checks and packages

On a computer with Python 3.11+ and Node (for syntax checks):

```sh
python tools/self_test.py
python tools/package.py --check
python tools/package.py --out dist
```

Tests never connect to a car, network or GitHub. Windows skips three Linux-only frame-file/process-group tests; Linux CI runs them. The packager emits:

* `shjeladze_jltube@0.4.0.tgz` — source package, no SDK, `build: "unit"` in the Catalog;
* `jltube-player@0.4.0.tgz` — tool kit (`component.json`, `files/`, `units/`);
* schema-2 `catalog.json` and `SHA256SUMS`.

By default the packages contain the locked diagnostic implementation and **no media runtimes**. The packager neither downloads nor executes external binaries. `requires` fields are minimum installed component versions, not exact dependency locks; `dependencies.lock.json` pins the upstream source revisions reviewed for this implementation. Pinning an upstream source revision does not prove ABI compatibility.

## Media runtime preparation (developer work remains)

The **Build portable media package** GitHub workflow now automates the pinned static-musl FFmpeg/QuickJS/OpenSSL build and the official yt-dlp download, offline decoder checks, corresponding-source archives, and media-inclusive Catalog packaging. See [native/runtime/README.md](native/runtime/README.md). A successful run supplies an Actions artifact; it does not establish real-car or audio compatibility. The manual preparation below remains available for reviewed target builds.

Use the small official yt-dlp **zipimport** `yt-dlp` artifact, not the large PyInstaller `yt-dlp_linux` executable. It includes EJS scripts and is launched with mgu-python 3.12. Do not rely on the head unit's Node 8 for YouTube challenges. The pinned candidate versions are yt-dlp `2026.10.26`, QuickJS `2026-06-04`, and FFmpeg `9.0.2`; their target-compatible build hashes are intentionally unselected until built and reviewed.

Build Linux x86-64 FFmpeg and QuickJS against a target-compatible libc/toolchain. Test on the actual firmware and record build flags, source hashes, compiler/sysroot hashes, runtime licenses and required shared libraries. FFmpeg needs HTTPS/TLS with trusted CA verification, HTTP demuxing, H.264 decoding, scaling, padding and raw YUV420P output. A host Ubuntu binary is not evidence of MGU compatibility. QuickJS's executable must be called `qjs`. The official yt-dlp/EJS distribution must pass a challenge resolution test without downloading remote components. No `--remote-components`, `--exec`, cookies, account login or self-update flags are enabled.

Prepare an untracked folder with `yt-dlp`, `ffmpeg`, `qjs`, `LICENSES.txt`, and `runtime-lock.json`:

```json
{
  "yt-dlp": {"version": "2026.10.26", "sha256": "<reviewed 64-character SHA-256>"},
  "ffmpeg": {"version": "9.0.2", "sha256": "<reviewed 64-character SHA-256>"},
  "qjs": {"version": "2026-06-04", "sha256": "<reviewed 64-character SHA-256>"}
}
```

```sh
python tools/package.py --runtime-dir vendor/runtime --out dist
```

This verifies supplied binary hashes and native ELF64/x86-64 headers, not the binaries' runtime behavior. Include all license obligations and corresponding source/build instructions when distributing runtimes. Keep binaries out of the repository tree; attach them only inside release assets. The media-inclusive package carries a root-owned `runtime-lock.json`, which the broker uses automatically when `binaries` is empty; an explicit root configuration can override the lock. Workers refuse missing or changed hashes.

## Vehicle adapter contract — no manual parked override

The included optional native bridge is documented in [docs/VEHICLE_BRIDGE.md](docs/VEHICLE_BRIDGE.md). It uses only getters, notifications and availability from the head unit's own native binding. Verify the exact interface, signal scaling, neutral/drive/reverse/Park encodings, invalid values, remote getter semantics and provider-loss behavior using the owner's local donor/interface data; never commit BMW SDK or signal catalogs. The OAP app is not trusted to assert that the vehicle is parked.

The external state-file contract below remains available when `vehicle_bridge.enabled` is false. Selecting the native bridge disables file fallback. The native bridge stays off by default, never imports a demo source, and does not start unless `vehicle_adapter_validated` is true.

The bridge must create `/run/jltube-vehicle` as root mode `0755`, and atomically replace its root-owned, non-group/world-writable `state.json` on every **new underlying measurement** (not by refreshing an old cached value):

```json
{"schema":1,"boot_id":"<current /proc/sys/kernel/random/boot_id>","monotonic":12345.6,"speed_mps":0,"gear":"P","valid":true}
```

`monotonic` is Linux CLOCK_MONOTONIC seconds from the same boot, not UTC or the phone's clock. Preserve the oldest of the speed/gear measurement times; require valid fresh measurements for both. Refresh faster than 500 ms; mark invalid or remove the file on disconnect, sleep or signal uncertainty. Reject inconsistent signals. No fake-state writer is installed. The optional native bridge uses private pipes instead of this file and includes the full challenge round-trip delay in sample age.

After real signal validation only, create `/var/opt/jltube-player/config.json` as root mode `0600`, in a root-owned, non-group/world-writable directory, using `native/jltube-player/config.example.json`. Leave `app_uid` null for automatic discovery from the authoritative deploy registry; an optional explicit value must match mgu-deploy status. Set `vehicle_adapter_validated` to true only after proving that adapter, and supply reviewed binary hashes. Restart the broker to load a changed configuration. Do not loosen state-file ownership or remove stale/unknown-state checks. An arbitrary root process can still bypass any software policy; root access is part of the trust boundary.

The watchdog checks every 100 ms, rejects a signal older than 500 ms, kills the complete media process group, and replaces the frame with black. The app also hides/drops the video on lockout and closes its renderer connection on losing focus. A lost app heartbeat stops the server's workers after 1.5 seconds. These are configured timing bounds, not measured real-car stopping guarantees. Confirm the physical display clears immediately on the target and that no cached or resumed playback survives a lockout. There is no automatic resume.

## Portal configuration

Once the adapter and runtimes have been validated, place `portal.json` in the installed OAP app's **data** directory, owned by that app (not in the versioned source tree):

```json
{"mode":"youtube","url":"https://www.youtube.com/watch?v=<video-id>"}
```

The **Open saved URL** button requests it. **Enter website URL** and **Enter YouTube video URL** open the in-app character-list keyboard while the broker reports a valid parked state. Select characters with the iDrive controller/touch, use **Next characters**, **Delete character**, and **Open**. Loss of authorization clears/closes entry; submission is checked again by the broker. This HMI behavior still requires target validation.

**Search YouTube** uses the same character keyboard for a plain-text search, including spaces. Select a returned video to request playback; result URLs are built only from valid YouTube video IDs. No general browser is used for this path. Results are cleared on lockout or stop. Live search/extraction has not been verified on a car and can be refused by YouTube or the current network.

`mode: "web"` with a user-entered HTTPS URL is accepted by the portal interface but currently returns **browser unavailable**. The Google button likewise reports that a full browser backend is missing. The Stop button is available regardless of parked state. Never place credentials in URLs. Only one video plays; no playlist, audio, download UI or background playback is offered.

## Catalog/Releases publishing

Follow the current [Store publishing guide](https://github.com/robertnisipeanu/mgu-store/blob/7d4d39bf2e449c6134178ac2198465252a526121/docs/PUBLISHING.md). There is intentionally **no `mgu-repo.json`** and no repo-tree build. After validation and an appropriate version bump:

```sh
python tools/package.py --runtime-dir vendor/runtime --out dist --base-url https://github.com/shjeladze/JLTube-MGU/releases/download/v0.4.0
```

Upload both `.tgz` assets to that version's GitHub Release; upload `catalog.json` to a release with tag/name `catalog`, as the Store requires. The Catalog must use the absolute release-download URLs generated by `--base-url`, not relative URLs for a GitHub Catalog release. For static HTTPS hosting or a USB folder, relative Catalog URLs work. A development package must be labelled experimental; do not present it as validated merely by creating a non-prerelease release.

In the Store, add `shjeladze/JLTube-MGU` on **Releases** once a Catalog release actually exists, or add an HTTPS Catalog URL. No release is automatically published by this repository or CI. Install the Store/mgu-deploy, mgu-render, mgu-python and mgu-uplink using their own upstream instructions first; the Catalog lists the player dependency before app installation. Confirm the Store reports Online with the chosen USB/tether/Wi-Fi connection. A normal head-unit restart may be required by its tool/recmgr installation lifecycle; follow the Store's pending-restart status.

For offline installation later, copy the generated Catalog and both packages to a USB source folder, or use the Store's `usb-repo` command with a published Catalog. USB installs do not make YouTube playable without an internet uplink.

## Diagnostics, acceptance and removal

On a development head unit, the read-only diagnostic command is:

```sh
/var/opt/mgu-python/current/bin/python3 /var/opt/jltube-player/current/player.py diagnostics
journalctl -u jltube-player.service -n 100 --no-pager
systemd-analyze verify /etc/systemd/system/jltube-player.service
```

`diagnostics` reports version, config, socket, runtime hashes and explicitly unavailable browser/audio. It does not claim live vehicle freshness or successful media decoding. Status errors also appear in the app. Logs omit URL strings, headers and subprocess stderr; external crash/core logging still needs target review.

Before treating this as a player, complete [docs/VALIDATION.md](docs/VALIDATION.md), including stop-on-motion, gear change while resolving/playing, stale/missing signals, app hide/HOME/BACK, renderer death, service death, bad network/DNS/TLS, suspend/restart and source-package linking from a local donor. Do not test driving video with a driver using the display; first prove movement-state injection with the vehicle stationary and use a controlled validation setup.

Remove the app and `jltube-player` through the Store. Stop the service before removing any manually installed vehicle bridge. Remove manually supplied configuration/bridge state only after review; this project never alters the stock firmware or installs the bridge itself. Keep shared mgu-render/uplink/python when other apps use them. Recmgr and head-unit-specific removal/restart behavior must be confirmed on target.

## Sources and license

Format review as of 2026-11-02 is pinned in `dependencies.lock.json`: [mgu-store](https://github.com/robertnisipeanu/mgu-store/tree/7d4d39bf2e449c6134178ac2198465252a526121), [idrive7-apps](https://github.com/cauliflowermossgrape/idrive7-apps/tree/0a3e7e1231e2c5871572352f99f702fc839b91f8), [IterioDev/car-apps](https://github.com/IterioDev/car-apps/tree/2a897bfdec8afe9246904fdebc5e5ae9b9c6fdc6). See the pinned [video protocol](https://github.com/robertnisipeanu/mgu-store/blob/7d4d39bf2e449c6134178ac2198465252a526121/native/mgu-render/PROTOCOL.md), [uplink requirements](https://github.com/robertnisipeanu/mgu-store/blob/7d4d39bf2e449c6134178ac2198465252a526121/native/mgu-uplink/README.md), and [yt-dlp EJS setup](https://github.com/yt-dlp/yt-dlp/wiki/EJS).

GPL-3.0-or-later; see [LICENSE](LICENSE). OAP permission/manifest structure is adapted from mgu-store (Robert Nisipeanu and IterioDev); no SDK code is included. The native service is an independent Python program, not a compiled player engine. This unofficial project is not affiliated with BMW or YouTube.
