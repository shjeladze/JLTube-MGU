# MGU Inspector 0.2.0 — private pairing, no SSH

Development source app + native tool for ID7/ID8. This version adds an Apps-menu pairing UI, loopback diagnostic service, no-SSH laptop client and Wi-Fi/network capability inventory. It does not provide arbitrary command execution, app installation, ECU coding or a universal browser/audio backend.

## Connection and permissions

`Inspector OAP tile → private Unix socket → root diagnostic service ← loopback:5891 ← existing Tailscale private network ← laptop client`

The service listens only on 127.0.0.1, never on the Wi-Fi interface or all interfaces. The separately installed upstream Tailscale tool proxies tailnet traffic to loopback. Both the car and laptop must already be logged into the same owner-controlled tailnet. Configure its ACL/grants to allow only your laptop/user to the car TCP port 5891; do not enable public Funnel, router port forwarding, subnet routing or expose a car management port to the internet. No network policy/account changes are made by this package.

The laptop checks its installed Tailscale status for a Running backend and the exact online peer IPv4 address before sending each request. It accepts only literal tailnet IPv4 addresses in 100.64.0.0/10, ignores HTTP proxy environment variables and refuses redirects. HTTP is carried inside Tailscale's encrypted private connection; this service itself does not implement TLS. Local root, the local OS/network route, the installed Tailscale software and the owner's tailnet are trusted. A private network is not permission to bypass pairing.

Only the exact installed shjeladze_inspector app UID, read from the root deploy registry, can use the private Unix pairing controls. Missing/ambiguous/stale registry data locks access. The app's Create pairing code action revokes prior access and generates a random 12-digit code for 120 seconds. Five failed attempts invalidate the code. A code can be used once; the resulting 256-bit session token lives only in memory and expires absolutely after 15 minutes. Disconnect/revoke works from the app or laptop. Restart removes all sessions. The app does not log the code. Token/code values never enter diagnostic reports or disk storage.

The read-only API has fixed JSON operations: summary, platform, graphics, browser, audio, network, safety and report. There is no shell string, file-path argument, upload endpoint or remote executable. HTTP Origin headers, duplicate headers, Transfer-Encoding, invalid lengths and oversized requests are refused. Inputs have time/size limits, up to 8 concurrent HTTP clients; systemd limits memory, tasks and descriptors. The service uses ProtectSystem=strict, NoNewPrivileges, ProtectHome and kernel/control-group protection. The read-only inventory does not open audio devices or subscribe to vehicle interfaces.

## Installation

Prerequisites: compatible MGU with custom app/tool installation access; Store/deploy >=0.7.0, mgu-python >=1.0.2, mgu-uplink, and IterioDev's Tailscale tool >=1.104.5. Add both shjeladze/JLTube-MGU and IterioDev/car-apps as sources when published; for this development bundle use its USB Catalog alongside the normal upstream sources. Dependencies must be present/downloadable; source packages link against the unit's own SDK. No SDK is distributed here.

1. Put the generated catalog.json and both .tgz files together in a Store USB source folder. Install MGU Inspector app; it requires the native tool. Follow Store pending-restart notices (ID8 app changes apply at startup).
2. Install/open IterioDev's Tailscale app from its normal source. Scan its login QR and approve your own device/account. Install Tailscale on the laptop and join the same private network. This is an explicit one-time user login; we cannot approve it automatically.
3. Open MGU Inspector in the car, select Create pairing code. Open CONNECT.cmd from the laptop bundle, enter the car's Tailscale IPv4 shown by Tailscale, and the code. Select Connect, then a report group. Save the report locally if needed.
4. Revoke access from either end when done. Remove the Inspector app and tool through Store to remove its service; keep shared Python/Tailscale/uplink dependencies when other apps need them.

This package does not unlock a stock car or set up a private network/account automatically. It is not a cloud relay and does not connect to ChatGPT directly. An assistant running on the authorized laptop can use the client or inspect saved reports when that laptop has connectivity. The CLI tools/inspector_pair_cli.py supports a hidden code prompt or --code-stdin for a one-shot report and revokes its token after collection. No password/private-key sharing or SSH command entry is required for the paired path.

## What we learn, and what remains unknown

The inventory reports allowlisted OS release fields, CPU/kernel/libc/Python, ID7/ID8 manager presence, selected installed component versions, graphics socket/device presence, candidate browser paths, namespace sysctls, ALSA card/PCM inventory and at most 32 network interface names/wireless flags/link states. No VIN, IP/MAC, SSID, passwords, tokens, SDK/definitions, process lists, journals, packet captures or general files are collected. Hardware/release strings remain untrusted data and should be reviewed before sharing. Reports are never uploaded automatically.

No Wi-Fi scan, network join, route/firewall change, subnet scan, CAN/UDS access or vehicle writes occur. Wi-Fi hotspot access is not whole-vehicle diagnostic access. MGU inventory cannot discover every ECU capability, establish a valid audio route or guarantee future software ideas without testing. A found device/path is not a working backend. Browser/audio/safety readiness stays false until independently integrated and validated.

Offline tests exercise expiry/replay/revocation, pairing attempt limits, exact app UID, HTTP framing/origin/auth rejection, output bounds, laptop protocol round trips against a localhost fixture, privacy allowlists and package hashes/reproducibility. Actual car installation, donor linking, Tailscale-to-car transport, systemd restrictions, HMI and Wi-Fi behavior have not been tested. The Tk desktop UI is syntax-checked; its interaction has not been exercised. This is a development package.

## Sources

- https://github.com/robertnisipeanu/mgu-store/blob/7d4d39bf2e449c6134178ac2198465252a526121/docs/PUBLISHING.md
- https://github.com/robertnisipeanu/mgu-store/blob/7d4d39bf2e449c6134178ac2198465252a526121/native/mgu-uplink/README.md
- https://github.com/IterioDev/car-apps/blob/2a897bfdec8afe9246904fdebc5e5ae9b9c6fdc6/README.md
- https://tailscale.com/docs/reference/faq/other-vpns

GPL-3.0-or-later; no affiliation with BMW or Tailscale. The OAP metadata structure is adapted from mgu-store. No BMW SDK files are shipped.
