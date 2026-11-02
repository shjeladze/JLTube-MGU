# Changelog

## 0.4.0

* Generate distinct ID7 and ID8 RHMI layouts and declare both HMI targets in the app, staged package, tool and Catalog.
* Add ID8 media-entry text-cell routing and the HMI 2 proxy declarations required by its local donor SDK; reject missing/ambiguous UI variants.
* Add an installation/service compatibility gate for x86-64 Linux and required shared components. Refuse unknown, ambiguous and non-x86 platforms explicitly.
* Add offline ID7/ID8 UI-routing, manifest/layout and platform-gate coverage. Audio, general browsing and real-car validation remain unresolved; this is not a universal production release.

## 0.3.1

* Add native YouTube search and a selectable results list using bounded yt-dlp metadata output. Construct playback URLs from validated video IDs; discard results if parked authorization is lost. YouTube search does not require a general browser engine.

* Add parked-only RHMI URL entry with separate website and YouTube-link modes; clear input and disable actions when authorization is lost.
* Add optional native read-only speed/selector reader. Track availability generations, reject delayed getters, expire speed and selector independently, and use private-pipe challenges with conservative round-trip accounting. No guessed P/N or demo fallback.
* Add a read-only SSH compatibility report that excludes VIN, keys, tokens and logs and retains strict host-key verification.
* Clear the video output before asynchronous cleanup, drain bounded child stdout after termination, bound process waits, and stop the broker if its watchdog unexpectedly exits.
* Add pipeline cleanup, bridge freshness, keyboard and Linux process-group/backpressure regression coverage.
* Include the full project license in generated OAP source packages.
* Add a Linux build pipeline for baseline x86-64 static-musl FFmpeg/QuickJS, static OpenSSL TLS, pinned official yt-dlp, corresponding-source archives and a media-inclusive development Catalog. It checks executable static linkage and decodes an offline H.264 fixture; it cannot prove real-car audio or safety behavior.

No claim of in-car validation, functional-safety certification, compatible Chromium/browser engine or working BMW audio routing is made. Native bridge activation, media runtimes and vehicle testing remain required.

## 0.3.0

Initial ID7 OAP source app, separate parked-only player broker/tool, YouTube/FFmpeg pipeline, mgu-render I420 output, mgu-uplink declarations, pinned candidate versions, diagnostics and reproducible development Catalog packaging. Browser and audio unavailable.
