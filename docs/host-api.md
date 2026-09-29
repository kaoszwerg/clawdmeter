# Clawdmeter host API — reference for client apps

A local HTTP API through which another app on the same Windows machine decides
what the Clawdmeter shows. Written for **yggshell**, which already drives a VITI
lamp as its *app*; the Clawdmeter is meant to be a second, selectable display
device behind the same signal ladder.

Everything below was checked against a running daemon and a real board
(Waveshare LCD-1.46, 2026-09-29). The responses are copied from those calls,
not written from memory.

---

## 1. The model

```
yggshell ──HTTP 127.0.0.1:47280──▶ Clawdmeter daemon ──BLE──▶ device
                                    (tray app, owns the link,
                                     polls the Anthropic quota)
```

- **The daemon is the only thing that talks Bluetooth to the device.** Do not
  open a BLE connection from the client. Two writers overwrite each other's
  animation, which is the same "two masters" problem ADR-PROJ-007 declined for
  VITI.
- **The client is the device's *app*, exactly as with VITI.** A state is
  announced and leads for **90 s**. A keep-alive every **30 s** holds it, and a
  release hands the choice back to the device.
- **The daemon keeps doing its own job regardless:** it polls the usage every
  60 s, pushes it to the device and reads the battery. The client only adds
  *which animation* plays; it never sends usage numbers.

### Differences to VITI a client must know

| | VITI (mirror) | Clawdmeter |
|---|---|---|
| After `release` | keeps the last colour **indefinitely** | goes back to its **own** animations (picked from the usage rate) |
| Client crashes / is killed | last colour stands until the app runs again | the **daemon** lapses the claim after 90 s; the device is back on its own choice |
| `off` | dark ring | **no dark state.** `off` means "release"; the device keeps showing usage and its own animation |
| Transport | LAN, plain HTTP, device serves it | **loopback only**, the daemon serves it; nothing leaves the machine |
| Key | typed from the device's UI | a file the daemon creates (§2) |

So `signal::hand_back`'s "set `off` first, then release" is harmless here but
not needed. A single `POST /api/release` is enough.

### Where the animation is visible

The device has two screens. The **splash** plays the animation full-size; the
**usage** view shows the numbers. The device returns to the splash by itself
after each short look at the usage (and the user can switch with the PWR key).
A claim is therefore always *in effect*, but visible whenever the splash is up.
There is no API to force a screen (see §8).

**Without a claim the device shows only neutral animations.** It rotates every
20 s through sleep / breathe / blink / look around / wink / dances, with the
group picked by how fast the quota is being used. The animations that stand
for a state are kept out of that rotation: `allow`, `done`, `work coding`,
`work think`, `think`, `write`, `limit` and `expression surprise`. So they
appear only when a host claims them, and "waiting for your approval" on the
device always means a client said so. (Pressing PWR on the device still steps
through every animation by hand.)

---

## 2. Finding the API and the key

| What | Where |
|---|---|
| Base URL | `http://127.0.0.1:47280` |
| Port override | `api_port = <n>` in `%LOCALAPPDATA%\Clawdmeter\config` (plain `key = value` lines, `#` comments). Only needed if 47280 is taken on the machine. **Clients should not parse that file**: offer a port field (default 47280) beside the key instead |
| Switch off | `api = off` in the same file (default: on) |
| Bearer key | `%LOCALAPPDATA%\Clawdmeter\api-key` (one line, created on first start) |
| Key for the user | tray icon → **Copy API key** |

Config changes take effect on the next daemon start.

The key file is readable by the Windows user who runs the daemon, the same
boundary the Claude OAuth token already sits behind. A client may **read the
file directly** (no user action), or let the user paste the key from the tray
menu. Either way, store it the way yggshell stores the VITI key, in the OS
keyring, and never return it from a command.

**Detecting the daemon:** `GET /api/info` needs no key. A refused connection
means that no daemon is running or that the API is switched off. Report it as
"Clawdmeter daemon not running", not as a device fault.

---

## 3. Authentication and errors

Every endpoint except `GET /api/info` needs

```
Authorization: Bearer <key>
```

Errors are JSON with one field, and **the status code carries the meaning**.
The `error` text is for logs: its wording is not part of the contract and may
change. A client should show its own sentence, keyed on the code (and on what
it sent), and may put the daemon's text in a detail line or the log.

```json
{"error": "missing or wrong bearer key"}
```

| Code | When |
|---|---|
| 400 | body is not a JSON object, neither or both of `status`/`anim`, unknown `status` or `anim` |
| 401 | missing or wrong key |
| 404 | unknown path |
| 405 | known path, wrong method (e.g. `GET /api/keepalive`) |
| 413 | body over 4 KiB |

Bodies are `Content-Type: application/json`. Trailing slashes and query strings
are ignored.

---

## 4. Endpoints

### `GET /api/info` — no key

Identifies the daemon and lists what it accepts. Read it once at connect time;
it replaces any hard-coded list in the client.

```json
{
  "device": "clawdmeter",
  "api": 1,
  "claim_s": 90,
  "keepalive_s": 30,
  "signals": {
    "busy": "allow",
    "call": "expression surprise",
    "away": "work coding",
    "focus": "work think",
    "free": "done",
    "off": ""
  },
  "wake_signals": ["busy", "call"],
  "animations": [
    "dance bounce dj", "dance sway dj", "dance djmix",
    "idle breathe", "idle blink", "idle look around",
    "work coding", "work think",
    "expression surprise", "expression sleep", "expression wink",
    "dance bounce", "dance sway",
    "done", "think", "write", "allow", "limit"
  ]
}
```

- `api` is the contract version. It goes up **only on a breaking change**
  (a field removed or renamed, a meaning changed, an endpoint gone). New fields
  and new animation names appear without a bump, so ignore fields you don't
  know. A client built for `api: 1` that sees any other number should **stop
  driving the device and say so** ("Clawdmeter daemon speaks API v2, this
  version of yggshell knows v1"), not guess.
- `signals` maps each VITI word to the animation the device plays for it. The
  mapping belongs to the daemon (see §5).
- `animations` is every name the firmware knows, taken from the firmware table
  and checked against it by a test.

### `GET /api/status`

Everything the daemon knows. Also the answer of every `POST`.

```json
{
  "source": "app",
  "hold_s": 88,
  "status": "busy",
  "anim": "allow",
  "shown": "allow",
  "paired": true,
  "connected": true,
  "address": "44:1B:F6:83:F3:41",
  "battery": 100,
  "usage": {
    "session_pct": 8,
    "session_reset_min": 13,
    "weekly_pct": 83,
    "weekly_reset_min": 1313,
    "status": "allowed",
    "account": "pro",
    "updated_at": 1790676442
  },
  "written_at": 1790676461,
  "error": null
}
```

| Field | Type | Meaning |
|---|---|---|
| `source` | `"app"` \| `"device"` | who decides the animation right now. `"device"` = no claim is held |
| `hold_s` | int | seconds left on the claim; `0` when `source` is `"device"` |
| `status` | string \| null | the signal word that was claimed; `null` if the claim was a raw `anim` or there is none |
| `anim` | string | the animation the claim asks for; `""` = the device's own choice |
| `shown` | string \| null | the `anim` value the **last successful BLE write** carried. `null` = nothing written on this link yet. **Not a read-back**: the firmware has no way to report what it plays, but a write that succeeded is taken by the firmware (serial log: `splash: host -> …`) |
| `paired` | bool \| null | Windows lists at least one paired Clawdmeter. `null` = the daemon has not looked yet (the first second after start). Updated on every connection attempt |
| `connected` | bool | the daemon holds a BLE link to the device |
| `address` | string \| null | BLE address of the device (the last one, if disconnected) |
| `battery` | int \| null | charge in %, from the device's Battery Level characteristic; `null` while disconnected or when the board has none |
| `usage` | object \| null | the last quota reading the daemon pushed; `null` until the first poll succeeded |
| `usage.session_pct` / `weekly_pct` | int | 0–100 (5-hour / 7-day window). On an enterprise plan `session_pct` is the overage utilization and `weekly_pct` is 0 |
| `usage.session_reset_min` / `weekly_reset_min` | int | minutes until that window resets, at the time of `updated_at` |
| `usage.status` | string | Anthropic's rate-limit status word, e.g. `allowed`, `allowed_warning`, `rejected` |
| `usage.account` | `"pro"` \| `"ent"` | plan type |
| `usage.updated_at` | int | Unix time of that reading |
| `written_at` | int \| null | Unix time of the last successful write to the device |
| `error` | string \| null | the last **write** failure; cleared by the next successful write. Nothing else sets it: a missing, unpaired or switched-off device is `null` here, not an error |

`battery` and `shown` are about the device; they go `null` the moment the link
drops, because a stale value is worse than none. `address` keeps the last
connected device for the life of the daemon process.

**Reading the device state for a panel** (absent values are not faults):

| `paired` | `connected` | Means | Say |
|---|---|---|---|
| `null` | `false` | daemon just started | "looking for the device" |
| `false` | `false` | no Clawdmeter is paired with Windows | "no device paired" |
| `true` | `false` | paired, but off / out of range / reconnecting | "device not reachable" |
| `true` | `true` | linked | show `battery`, `shown`, `usage` |

`usage` stays `null` until the first reading reached a connected device: the
daemon only polls the quota while it holds a link.

### `POST /api/status` — claim

Body: **exactly one** of

```json
{"status": "busy"}
```

```json
{"anim": "dance bounce"}
```

- `status`: one of the six VITI words. The daemon maps it (§5). `"off"`
  releases the claim instead of claiming, and its answer is **exactly** the
  answer of `POST /api/release`: `source: "device"`, `hold_s: 0`,
  `status: null`, `anim: ""`. There is nothing to tell the two apart by, and
  nothing that needs to be.
- `anim`: any name from `/api/info`'s `animations`, played verbatim. This is for
  what the ladder does not cover, e.g. a celebration. Prefer `status` for the
  ladder itself, so the mapping stays in one place.

**A claim keeps the panel lit.** The device switches its screen off after a
spell without touches (`sleep` in the daemon config, 30 min by default), but
not while a client holds a claim: any claimed state — `away` included — lights
a dark panel and keeps it on, and the idle timer only starts once the claim is
released or lapses. `busy` and `call` (listed as `wake_signals` in
`/api/info`) additionally send an explicit wake with the change; with the
current firmware that is redundant, and it keeps an older firmware waking for
the two states that exist to be seen.

The claim leads for `claim_s` (90 s) from this call. **The daemon writes to
the device at once**, not at its next 60-second poll: measured on hardware,
the write went out in the same second as the request. Claiming the animation
that is already claimed only renews the hold and sends nothing.

Answer: the status object. Right after the call `shown` may still be the
previous value; the write lands a moment later, and the next keep-alive
reports it.

If the device is disconnected, the claim is still accepted and held. It is
written as soon as the link is back, if it has not lapsed by then.

### `POST /api/keepalive`

No body. Extends a held claim to a full `claim_s` again and answers the status.
**If there is no claim** (it lapsed, was released, or the daemon restarted),
nothing is revived: the answer shows `"source": "device"`. That answer is the
signal to claim again (§6).

### `POST /api/release`

No body. Drops the claim. The daemon writes `""` to the device, and the device
goes back to picking its own animation. Answers the status (`"source":
"device"`). Releasing without a claim is harmless.

---

## 5. The signal mapping

| yggshell `Signal` | Ladder meaning | Device plays |
|---|---|---|
| `busy` | blocked on **you** — a question, a permission | `allow` |
| `call` | a fault you would otherwise not notice | `expression surprise` |
| `away` | at least one agent is working | `work coding` |
| `focus` | no turn open, background work still running | `work think` |
| `free` | every agent is finished | `done` |
| `off` | no agent running | *(release — the device's own choice)* |

The mapping is the daemon's, as the colour is VITI's: the client names a
**meaning**, the device side chooses the picture. If it changes, `/api/info`
reports the new one; the client needs no update.

---

## 6. How yggshell should drive it

This is the loop yggshell already runs for VITI (`signal::start`), with a
second transport. Nothing in the ladder (`signal::roll::decide`) changes.

**Map the VITI functions one to one:**

| `signal::viti` | Clawdmeter call |
|---|---|
| `info(host)` | `GET /api/info` (no key) |
| `status(device)` | `GET /api/status` |
| `show(device, signal)` | `POST /api/status {"status": signal.wire()}` |
| `keepalive(device)` | `POST /api/keepalive` |
| `release(device)` | `POST /api/release` |
| `brightness(device, n)` | *not available* (§8) — hide the control for this device |

**Loop rules:**

1. Decide the signal with the existing ladder.
2. **Write only on change.** A changed signal → `POST /api/status`.
3. **Keep-alive every `keepalive_s` (30 s)** while a signal other than `off`
   is shown. Loopback is cheap, but the rule keeps the two devices
   interchangeable.
4. **Read the keep-alive's answer, don't just await it** — the lesson of
   `signal::forgotten`:
   - `source == "device"` while you believe you hold a claim → the daemon was
     restarted or the claim lapsed → send `POST /api/status` again at once.
   - `connected == false` → the device is off or out of range. The claim is
     still held and will be delivered on reconnect; show it in the tool panel
     (like VITI's `link`), do not treat it as an error of yours.
   - Compare against the daemon's own words (`status`/`anim`/`shown`), never
     against what you meant to send, the same rule ADR-PROJ-007 sets for VITI.
5. **On quit / switch-off:** `POST /api/release`. If yggshell dies without it,
   the daemon lapses the claim after 90 s.
6. **Selecting the device** (VITI or Clawdmeter) is a setting; nothing stops a
   user from driving both at once, since they are independent devices behind
   independent transports.

**Minimal client, as a transcript** (bash; replace with reqwest):

```bash
KEY=$(cat "$LOCALAPPDATA/Clawdmeter/api-key")
H="Authorization: Bearer $KEY"
curl -s http://127.0.0.1:47280/api/info                               # detect
curl -s -X POST -H "$H" -d '{"status":"away"}' http://127.0.0.1:47280/api/status
curl -s -X POST -H "$H" http://127.0.0.1:47280/api/keepalive           # every 30 s
curl -s -X POST -H "$H" http://127.0.0.1:47280/api/release             # on quit
```

**Showing it in the tool panel:** everything VITI's panel shows has a
counterpart except the orientation fields. Worth displaying are `connected`,
`battery`, `source`/`hold_s`, `shown`, and `usage` (session and weekly % with
the reset countdown). The usage duplicates what yggshell may already show, but
it is *what the device displays*, so it confirms the device is current.

---

## 7. Timing, measured

| | |
|---|---|
| claim → BLE write | same second (event-driven, no poll wait) |
| lapse after the last claim/keep-alive | 90 s, noticed within the daemon's 5 s tick |
| usage refresh | every 60 s, or at once when the device asks (its refresh characteristic) |
| daemon restart | claim lost → the next keep-alive answers `source: "device"` |

---

## 8. What the API cannot do (yet)

| Feature | Why not | What it would take |
|---|---|---|
| Brightness | not in the BLE protocol; the device sets it with its own keys | a payload field + firmware change |
| Forcing a screen (splash / usage) | same | same |
| A dark / off state | the device has none; it always shows usage. (It does switch its screen off after `sleep` minutes without a touch, set in the daemon config, not through the API) | firmware change |
| The device's buttons | they are a BLE **HID keyboard** straight to Windows (BOOT = Space, the secondary = Shift+Tab). They never pass through the daemon | nothing — they already work in any terminal |
| Pairing | on the device (hold PWR) and in Windows Bluetooth settings | — |
| macOS / Linux | the API is in the Windows daemon only | the same module in `claude_usage_daemon.py` |

---

## 9. Implementation notes (daemon side)

- `daemon/host_api.py`: claim rules (`HostState`), mapping, HTTP server
  (stdlib, loopback, one thread).
- `daemon/claude_usage_daemon_windows.py`: adds `"a"` to every payload, resends
  the last reading with a fresh clock when only the animation changed, and
  reads the Battery Level characteristic.
- Tests: `daemon/tests/test_host_api.py`. They cover the claim rules with a
  fake clock, the HTTP surface on a real socket, and the animation list
  against `firmware/src/splash_animations.h`.
