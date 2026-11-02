# Native ID7 vehicle-state bridge (0.3.1)

An optional root-owned SOME/IP reader is now included. It is disabled by default and has not been tested on an MGU. It cannot be enabled from the OAP app. Enabling a reader whose getter semantics have not been verified would undermine the parked-only policy.

The reader uses `require('someip')` from the head unit's own Node/native binding. It never loads BMW SDK code from this repository. If the system Node process cannot resolve or use that binding, the reader fails and playback remains locked; do not copy an arbitrary addon from a different firmware.

The field candidates, based on the pinned idrive7-apps reader, are:

| Interface | Instance | Field | Input |
| --- | --- | --- | --- |
| de.bmw.infotainment.vehicle.Vehicle2 | 1 | statusCarSpeed2 | speedVehicleCentreOfGravity, raw / 64 km/h; 65535 invalid |
| de.bmw.infrastructure.VehicleInformation | 1 | statusGearboxDrive | statusActualStageDrive, P/R/N/D or 1/2/3/4 |

These are candidates for validation on the owner's firmware, not universal BMW safety definitions. No fallback from an engaged-gear signal, no `N_OR_P`, no RPM-based estimate, and no demo source is accepted.

## Local firmware prerequisites

1. Obtain the two generated SOME/IP interface definitions locally from the unit's own generator and master catalog. Verify field structures, raw invalid markers, enum encodings, transport availability semantics and read permissions. Do not publish the definitions or SDK.
2. Verify that `getValue(field, timeout)` performs a fresh remote getter transaction, rather than returning a locally cached subscription value. Confirm that the remote provider itself updates the fields correctly. If a getter is absent, cached, or its freshness cannot be established, retain the locked state and use a separately validated sensor adapter instead.
3. Place the definitions as root under `/var/opt/jltube-player/vehicle/someipInterfaces/` named `de_bmw_infotainment_vehicle_Vehicle2.json` and `de_bmw_infrastructure_VehicleInformation.json`. Every parent must be root-owned and not group/world writable. The broker verifies ownership and rejects symlinks.
4. After proving those semantics, create root-owned `/var/opt/jltube-player/vehicle/config.json` with `{"confirmed_remote_getters": true}` and mode `0600`. In the broker's root configuration set `vehicle_bridge.enabled` and `vehicle_adapter_validated` to true. The latter is a validation latch, not evidence that validation occurred.
5. Verify startup, speed/selector invalid values, individual provider disconnects, bus silence, native binding failure and suspend/resume while the car is stationary. Record physical screen-clearing time before considering any driving-state validation.

## Freshness and trust

The bridge polls each remote getter at most once every 100 ms, never overlaps requests for the same field, and refuses responses older than 250 ms. Availability changes and notification events invalidate outstanding generations; an old response cannot become current after a reconnect. The speed and selector each expire independently; one signal cannot refresh the other.

The Python broker talks to the root-owned child through private inherited pipes. Each sample must answer a new random challenge. The broker adds the entire round-trip delay to the bridge-reported age, so a buffered old reply cannot be timestamped as fresh. Mismatched challenge, malformed output, EOF, timeout, native error or either stale signal removes the internal state. Selecting this bridge disables fallback to the external state file. The app/control socket has no bridge-input or unlock operation.

The root service reads only getters, subscriptions and availability; it does not call setters, diagnostic services, coding or ECUs' write methods. This does not prove that the firmware's data source is safety-rated or that its timing is sufficient. The browser and audio remain separate unresolved target integrations.

## Collect a target compatibility report

With an already verified SSH host key and the Store's mgu-python installed, run on the computer:

```sh
python tools/collect_target.py --host <head-unit-IP> --identity <existing-SSH-key> --out target-report.json
```

This sends the fixed `preflight.py` program through SSH standard input. It installs no files and reads no VIN, keys, tokens, browsing history or vehicle logs. It reports selected OS/build identifiers, architecture, libc/kernel, Python/Node/systemd availability, component presence and CA/socket availability. It does not enable SSH, weaken host-key checking, identify a car on the network or change the vehicle. If SSH or Python is unavailable, it stops and reports that prerequisite instead of attempting installation.
