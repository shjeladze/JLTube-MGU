# MGU Inspector 0.1.0 — read-only development tool

An installable Store **tool**, not a tile in the BMW Apps menu. It provides fixed inventory operations over the owner's existing SSH connection. It has no daemon, listening port, internet permission, startup job, downloaded code, shell-command API or vehicle writes. Installation/removal uses the existing Store/deploy framework. No BMW SDK is distributed.

## What it can tell us

`summary`, `platform`, `graphics`, `browser`, `audio`, `safety`, or the combined `report`. These report known OS release fields, CPU/kernel/libc/Python, ID7/ID8 manager presence, selected installed component versions, fixed graphics socket/device paths, candidate browser paths, namespace sysctl values, and ALSA card/PCM inventory. It does not open audio devices, request media focus, connect to vehicle interfaces, change files or attempt playback. Unknowns stay unknown; a detected path never proves a working backend.

No VIN, hostname, IP/MAC, keys, cookies, account credentials, general environment, process list, journal, BMW SDK/definitions or arbitrary files are collected. Reports are data, not instructions. Fixed hardware/release strings should still be reviewed before sharing. No report is uploaded automatically.

## Installation and connection

Prerequisites: compatible ID7/ID8 MGU with custom-tool installation access, Store/deploy, mgu-python >=1.0.2, and an owner-controlled SSH connection with a verified host key. This tool neither unlocks stock vehicles nor sets up SSH. A read-only report cannot make every application compatible.

1. Build with `python tools/package_inspector.py --out dist/inspector`, or use the generated development kit/Catalog. Put `catalog.json` and the `.tgz` together in a Store USB source folder. Install **MGU Inspector (read-only development)** under Tools, following the Store's USB source flow. This package itself needs no restart/service; follow any dependency pending-reboot notices. Do not unpack/copy files into firmware folders manually.
2. From the laptop, with the existing host key and identity already configured:

   The downloadable bundle also includes `CONNECT.cmd` and a Python/Tk desktop client with host/identity fields, an allowlisted operation selector and a local JSON export button. It uses the same SSH connector and does not save credentials or upload reports. Python 3 with Tk and the OpenSSH client are prerequisites.

   ```sh
   python tools/inspector_connect.py --host YOUR_MGU_SSH_ALIAS --operation report --out mgu-report.json
   ```

   Optional `--identity` selects a local private-key file; it is used by the installed SSH client and never read or included in a report. Never send its contents. The client checks host keys strictly, disables agent/X11/port forwarding, requests a single fixed command, caps output at 128 KiB and ends after 25 seconds. There is no remote arbitrary-command field.
3. The report is saved locally. An assistant with authorized access to that laptop and network can run the same connector and inspect the result. Installing the tool **does not connect ChatGPT automatically** or grant access to the car. Remote access requires an already functioning owner-controlled private connection; do not expose SSH to the public internet. Existing upstream private networking can be used separately; this tool does not provision it.

On the unit, the equivalent fixed invocation is:

```sh
/var/opt/mgu-python/current/bin/python3 /var/opt/mgu-inspector/current/inspector.py report
```

Uninstall through Store Tools. There is no persistent process, account or network rule created by this component. Install/removal themselves are privileged deploy operations; the inventory program only reads.

## Scope and validation

This is an initial diagnostic component, not an unrestricted remote executor or a universal app installer. Browser packaging, audio routing, donor linking, vehicle-state validation and production deployment remain separate engineering work. The read-only operations do not require or assert a parked signal; perform setup while stationary. No diagnostic success enables video playback.

Offline fixtures cover both HMI layouts, redaction/allowlists, size limits, command-injection refusal and artifact hashes. Real-car installation and SSH collection have not been run. A future write/deploy operation must be a separate, explicit reviewed update with integrity checks, rollback and vehicle-state prerequisites, rather than arbitrary instructions executing as root.
