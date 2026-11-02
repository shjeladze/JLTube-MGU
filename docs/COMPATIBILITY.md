# ID7 and ID8 compatibility — 0.4.0

The project now generates one OAP source package with two native RHMI descriptions, ID7 and ID8. This removes the ID7-only manifest restriction and shares the YouTube search/player controller. It is an experimental cross-platform implementation, not a claim that every BMW head unit has been validated.

| Capability | ID7 implementation | ID8 implementation | Target evidence |
| --- | --- | --- | --- |
| Native page | LT_State_Wide | LT_State_Wide_List | Shapes based on pinned mgu-store descriptions; no car/emulator execution here |
| Button widget | LT_Button_1Row | LT_Button_MediaEntry_1Row | XML/JSON verified in offline checks |
| Button text | Text | PrimaryText | Runtime routing tested for both |
| Labels/title | Text | Text | Runtime routing tested |
| HMI proxies | RemoteHmi/EntryPoint/ResourceManagement | RemoteHmi2/EntryPoint2/ResourceManagement2 and PrivateEntryPoint2 | Locally linked donor and startup still need target validation |
| Renderer | Current native mgu-render video protocol | Same protocol, negotiated app area | Protocol bytes and fast stream switching tested; no physical display measurement |
| Native media CPU | Little-endian x86-64 Linux, static musl | Same architecture only | Static Linux build/offline decode; ARM is refused |
| Safety signals | Optional read-only bridge | Same bridge interface candidates | Neither firmware profile certified; defaults remain locked |
| Audio | Disabled | Disabled | BMW media-session/focus/PCM route unresolved |
| General browser | Unavailable | Unavailable | No compatible engine selected |

## Installation gate

App identity is discovered automatically from the root deploy tool's exact `shjeladze_jltube` app entry and verified against the Unix peer UID. The mapping expires after 2.5 seconds without a fresh authoritative registry response; another app's UID, a duplicate entry, worker/root UID or missing registration is rejected. No per-VIN binding is used. An explicit root `app_uid` configuration remains an optional operator override, not a requirement of the default installation.

`compat-check.js` is both the tool's deploy `check` hook and its service's first `ExecStartPre`. It checks Linux, little-endian x86-64, exactly one known OAP manager folder, and the installed Python, CA bundle, renderer and unshare prerequisites. An unknown/ambiguous platform, ARM/32-bit CPU or missing prerequisite yields explicit JSON errors and exit status 2. It makes no configuration changes and never reports a real-car validation success.

The app identifies the actual active RHMI variant from its generated hidden HMI marker. Missing or contradictory markers fail initialization instead of silently applying ID7 fields to an ID8 screen. The renderer obtains display placement from X_READY rather than assuming a single display size. No VIN, model/year or per-car identifier is used to select the UI.

## Limit of “any BMW”

An ID7/ID8 label alone does not establish CPU, kernel, firmware interfaces, donor SDK, custom-app access, audio routing or renderer availability. This package is intended for compatible MGU OAP environments with the Store/deploy framework, not for locked stock vehicles without custom-app installation access, other CPU architectures, ID9/Android Automotive or every later BMW software platform.

Declaring both HMIs permits the Store to evaluate the package for both. It does not turn the unresolved audio, safety integration or physical validation into completed functionality. The user is not being asked to guess an audio device or disable the lockout. Those integrations must be completed with trustworthy platform evidence before a production-ready universal app can be claimed.
