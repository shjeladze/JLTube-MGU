# Validation record — 0.3.1

This record distinguishes offline evidence from target behavior. No real-car tests have been performed.

| Check | Evidence/status |
| --- | --- |
| Repository starting state | `main` c9b8299: README only; no implementation to preserve |
| Current public formats | Reviewed mgu-store, idrive7-apps, IterioDev pinned commits in dependencies.lock.json |
| Windows offline self-test | 22 Python tests: 19 passed, 3 Linux-only tests skipped; JavaScript keyboard/action/bridge-state checks, manifests and Node syntax passed |
| Reproducibility | Two builds compared byte-for-byte by automated test |
| Package integrity | Catalog size/SHA-256 and every tool file hash checked by automated test |
| SDK exclusion | Source-package allowlist; no node_modules/oap-sdk, firmware, donor bundle or compiled app.js |
| Parked-state policy | Zero speed + P + valid + same boot + <=500 ms; malformed, stale, future, nonfinite and non-P cases tested |
| IPC | Exact configured app UID; root/other app rejected; no vehicle/unlock op; output cap tested |
| Watchdog | Running-task cancellation on motion and app-heartbeat loss tested with fake playback |
| Linux frame IO/process cleanup | Included in CI; not executed on Windows |
| CI after remote commit | Inspect GitHub Actions; not presumed passed |
| Actual OAP donor linking and HMI focus/entry lifecycle | NOT TESTED; local owner-supplied donor required |
| Linux native decoder/resolver/EJS pipeline | NOT TESTED; no target-compatible runtimes supplied |
| systemd 237 + unshare + resolver namespace + recmgr | NOT TESTED on head unit |
| UID 3921 availability and uplink firewall/routing | Startup account/process collision refusal implemented; target inventory and network tests required |
| Vehicle speed/Park signal bridge | Native read-only bridge implemented; challenge/response transport ages and signal expiry tested; actual binding, getter semantics and definitions NOT VALIDATED on target |
| In-car URL entry | RHMI keyboard implemented; pure keyboard tests passed; physical controller/touch/focus NOT VALIDATED |
| Full browser engine | NOT IMPLEMENTED; target compatibility report required before selecting a runtime |
| Audio routing and media session | NOT IMPLEMENTED; audio deliberately disabled |

## Required target acceptance evidence

Record firmware/HMI version without VIN, exact donor SDK version, installed component versions, runtime hashes, target ABI/kernel, and test date. Keep private donor/interface data outside this repository.

1. Link and start source package using the unit's own donor; show the tile, correct text/icon, focus, HOME/BACK, restart and removal. Validate that SDK code appears only in the locally built installed package.
2. Prove root-owned state input cannot be written by OAP UID/worker UID. Prove a non-JLTube app cannot use the broker. Confirm no network listener and no privilege retention in workers (`Uid`, `Gid`, `Groups`, `CapEff`, `NoNewPrivs`).
3. Implement and validate real read-only speed and selector subscriptions. Confirm invalid/unavailable/P/N/D/R encodings and units. Halt updates independently for each signal. Confirm stale data never gets retimestamped as a fresh measurement.
4. Measure time from nonzero speed, selector leaving P, invalid sample, state-file removal, bridge crash and suspend/resume to worker termination and physical screen clearing. Repeat during resolution, decoder startup and playback; confirm no automatic restart of media.
5. Verify MGVF header, I420 plane order, three-slot publication, color matrix/range and root ownership against actual mgu-render. Test missing video capability, renderer socket loss, wrong dimensions, foreground switching and cached frame clearing. Never cover the camera/stock safety UI.
6. Validate Python stdlib/SSL availability, CA path, correct clock, old systemd directive support, mount namespace isolation, process-group cleanup, 3921 UID allocation, uplink DNS changes, offline reconnect and firewall behavior without changing the stock resolver/default route.
7. Supply reviewed target-compatible media runtimes. Resolve a public video with bundled EJS and QuickJS, decode at 360p/24 without audio, and measure CPU/RAM/temperature. Verify format unavailability, geo/age/account restrictions, resolver failure, expired URLs, TLS failure, reconnect and oversized/malicious resolver output are actionable failures.
8. A future browser must retain its own sandbox and public-only network isolation, enforce the same parked/heartbeat checks for every process/navigation/input, and clear its displayed output on lock. Validate arbitrary URL handling, redirects, certificate errors, keyboard/controller/touch, GPU/software rendering and memory on the actual MGU. Until then, retain explicit unavailable responses.
9. A future audio implementation must validate the BMW media-session/audio-focus route, mute/duck behavior, no playback while locked, suspend/resume, navigation/call/camera interruption and recovery. Do not route directly to guessed ALSA devices or assume video success proves audio success.
10. Verify tool update, rollback, uninstall and recmgr restart rules while the car remains stationary and on stable power. Record failures and update this file with actual evidence, never inferred success.

The parked-only checks are defensive software controls, not a functional-safety certification. No 100% working or safety guarantee is made.
