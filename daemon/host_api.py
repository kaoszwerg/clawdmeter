"""Local host API: lets another app on this machine drive the Clawdmeter.

The daemon owns the Bluetooth link and keeps doing so. A second app — the
first client is yggshell — does not talk BLE itself; it asks this API, and the
daemon carries the request to the device in its next write. One writer per
device, so two programs never overwrite each other's animation.

The shape deliberately follows the VITI lamp's HTTP API (the *app* role): a
state is announced with ``POST /api/status`` and leads for ``CLAIM_SECONDS``,
``POST /api/keepalive`` extends it, ``POST /api/release`` hands the choice back
to the device. A client written against VITI needs a second transport, not a
second model.

Two differences to VITI, both in the client's favour:

- **A released Clawdmeter falls back to its own animations.** Its firmware
  picks them from the usage rate, so nothing stands "for ever" the way a VITI
  mirror keeps its last colour. Darkening before releasing is unnecessary.
- **A claim that is not renewed lapses here, in the daemon.** If the client
  crashes, the device is back on its own choice within ``CLAIM_SECONDS``.

Reference for client authors: docs/host-api.md.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import re
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

API_VERSION = 1
DEFAULT_PORT = 47280
CLAIM_SECONDS = 90
KEEPALIVE_SECONDS = 30

# Every animation the firmware knows, by the name the BLE payload's "a" field
# takes. Mirrors the table at the end of firmware/src/splash_animations.h;
# tests/test_host_api.py fails if the two drift apart.
ANIMATIONS = (
    "dance bounce dj", "dance sway dj", "dance djmix",
    "idle breathe", "idle blink", "idle look around",
    "work coding", "work think",
    "expression surprise", "expression sleep", "expression wink",
    "dance bounce", "dance sway",
    "done", "think", "write", "allow", "limit",
)

# Claims of these signals also light a dark panel: they are the two states
# that exist to be seen (a question waiting on you, a hidden fault).
WAKE_SIGNALS = ("busy", "call")

# The six VITI signal words, and what the device plays for each. The mapping
# is the device side's to keep — a client names a meaning, not a picture.
# "off" has no animation: it releases the claim, so the device goes back to
# choosing by itself (a Clawdmeter has no dark state to show).
SIGNALS = {
    "busy":  "allow",                # blocked on you: a question, a permission
    "call":  "expression surprise",  # a fault you would otherwise not notice
    "away":  "work coding",          # at least one agent is working
    "focus": "work think",           # no turn open, background work still running
    "free":  "done",                 # every agent is finished
    "off":   "",                     # no agent running: hand back to the device
}


class ApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


class HostState:
    """Everything the API reports and decides, behind one lock.

    Written from two threads: the HTTP server's (claims) and the daemon's
    asyncio loop (link, battery, usage, what was written). Pure bookkeeping —
    no I/O — so the claim rules are testable with a fake clock.
    """

    def __init__(self, clock=time.time) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        # claim
        self._signal: str | None = None
        self._anim = ""
        self._claimed_until = 0.0
        # device side, filled in by the daemon
        self._connected = False
        self._paired: bool | None = None    # None = not looked yet
        self._address: str | None = None
        self._battery: int | None = None
        self._usage: dict | None = None
        self._usage_at: float | None = None
        self._shown: str | None = None      # None = nothing written this link
        self._written_at: float | None = None
        self._error: str | None = None
        self._wake_pending = False
        # wake-up for the daemon loop; attached per asyncio loop
        self._loop: asyncio.AbstractEventLoop | None = None
        self._changed: asyncio.Event | None = None

    # ---- the daemon's side -------------------------------------------------

    def attach(self, loop: asyncio.AbstractEventLoop, changed: asyncio.Event) -> None:
        """Wake `changed` on `loop` whenever a client changes the claim.

        Re-attached on every daemon run: the tray restarts a crashed loop with a
        fresh asyncio.run(), and an Event belongs to the loop it was made on.
        """
        with self._lock:
            self._loop = loop
            self._changed = changed

    def wanted_anim(self) -> str:
        """The animation the device should play now; "" = its own choice.

        Lapses the claim on the way — the daemon asks every tick, so an
        abandoned claim ends within a tick of CLAIM_SECONDS.
        """
        with self._lock:
            self._expire_locked()
            return self._anim

    def take_wake(self) -> bool:
        """True once after a claim that should light the panel."""
        with self._lock:
            pending, self._wake_pending = self._wake_pending, False
            return pending

    def request_wake(self) -> None:
        with self._lock:
            self._wake_pending = True

    def set_link(self, connected: bool, address: str | None = None) -> None:
        with self._lock:
            self._connected = connected
            if connected:
                self._address = address
            else:
                # Unknown, not "as last seen": a stale battery value or a stale
                # "shown" would be worse than none.
                self._battery = None
                self._shown = None

    def set_paired(self, paired: bool) -> None:
        """Whether Windows lists at least one paired Clawdmeter."""
        with self._lock:
            self._paired = paired

    def set_battery(self, pct: int | None) -> None:
        with self._lock:
            ok = isinstance(pct, int) and 0 <= pct <= 100
            self._battery = pct if ok else None

    def set_usage(self, payload: dict) -> None:
        with self._lock:
            self._usage = dict(payload)
            self._usage_at = self._clock()

    def set_written(self, anim: str) -> None:
        """Record the animation the last successful BLE write carried."""
        with self._lock:
            self._shown = anim
            self._written_at = self._clock()
            self._error = None

    def set_error(self, message: str | None) -> None:
        with self._lock:
            self._error = message

    # ---- the client's side -------------------------------------------------

    def claim(self, body: dict) -> dict:
        signal = body.get("status")
        anim = body.get("anim")
        if (signal is None) == (anim is None):
            raise ApiError(400, 'send exactly one of "status" or "anim"')
        if signal is not None:
            if signal not in SIGNALS:
                raise ApiError(400, f"unknown status {signal!r}; one of {sorted(SIGNALS)}")
            if signal == "off":
                return self.release()
            target = SIGNALS[signal]
        else:
            if anim not in ANIMATIONS:
                raise ApiError(400, f"unknown anim {anim!r}; see GET /api/info")
            target = anim
        with self._lock:
            changed = target != self._anim
            if changed and signal in WAKE_SIGNALS:
                self._wake_pending = True
            self._signal = signal
            self._anim = target
            self._claimed_until = self._clock() + CLAIM_SECONDS
        if changed:
            self._wake()
        return self.status()

    def keepalive(self) -> dict:
        with self._lock:
            self._expire_locked()
            if self._anim:
                self._claimed_until = self._clock() + CLAIM_SECONDS
        return self.status()

    def release(self) -> dict:
        with self._lock:
            changed = bool(self._anim)
            self._drop_locked()
        if changed:
            self._wake()
        return self.status()

    def status(self) -> dict:
        with self._lock:
            self._expire_locked()
            now = self._clock()
            leading = bool(self._anim)
            usage = None
            if self._usage is not None:
                u = self._usage
                usage = {
                    "session_pct": u.get("s"),
                    "session_reset_min": u.get("sr"),
                    "weekly_pct": u.get("w"),
                    "weekly_reset_min": u.get("wr"),
                    "status": u.get("st"),
                    "account": u.get("acct"),
                    "updated_at": int(self._usage_at) if self._usage_at else None,
                }
            return {
                "source": "app" if leading else "device",
                "hold_s": max(0, int(round(self._claimed_until - now))) if leading else 0,
                "status": self._signal if leading else None,
                "anim": self._anim,
                "shown": self._shown,
                "paired": self._paired,
                "connected": self._connected,
                "address": self._address,
                "battery": self._battery,
                "usage": usage,
                "written_at": int(self._written_at) if self._written_at else None,
                "error": self._error,
            }

    # ---- internals ---------------------------------------------------------

    def _expire_locked(self) -> None:
        if self._anim and self._clock() >= self._claimed_until:
            self._drop_locked()

    def _drop_locked(self) -> None:
        self._signal = None
        self._anim = ""
        self._claimed_until = 0.0

    def _wake(self) -> None:
        with self._lock:
            loop, event = self._loop, self._changed
        if loop is not None and event is not None:
            try:
                loop.call_soon_threadsafe(event.set)
            except RuntimeError:
                pass   # loop already closed; the next run re-attaches


def info() -> dict:
    return {
        "device": "clawdmeter",
        "api": API_VERSION,
        "claim_s": CLAIM_SECONDS,
        "keepalive_s": KEEPALIVE_SECONDS,
        "signals": {k: v for k, v in SIGNALS.items()},
        "wake_signals": list(WAKE_SIGNALS),
        "animations": list(ANIMATIONS),
        "prove": True,
        "sign": True,
    }


# ---------------------------------------------------------------------------
# Proving the key without sending it
# ---------------------------------------------------------------------------

# The text the proof is made over, before the nonce. yggshell's
# signal::clawdmeter::PROVE_LABEL must be the same bytes; both sides pin one
# shared vector (test_prove_matches_the_shared_vector).
PROVE_LABEL = b"clawdmeter host-api prove v1\n"

# 32 to 128 hex characters: at least 16 random bytes, and nothing that is not
# a nonce can be smuggled through it.
_NONCE = re.compile(r"[0-9a-fA-F]{32,128}")


def prove(key: str, nonce: str) -> str:
    """What a holder of `key` answers to `nonce`: HMAC-SHA256, lowercase hex.

    A client sends a fresh random nonce before it sends the bearer key, and
    sends the key only if the answer is right. Something else listening on the
    port — another account's program while this daemon is down, which is the
    case yggshell's security audit (N4) is about — cannot make it without the
    key, so it never receives the key. The key itself never travels for this.
    """
    return hmac.new(key.encode(), PROVE_LABEL + nonce.encode(), hashlib.sha256).hexdigest()


def prove_answer(key: str, body: dict) -> dict:
    nonce = body.get("nonce")
    if not isinstance(nonce, str) or not _NONCE.fullmatch(nonce):
        raise ApiError(400, '"nonce" must be 32 to 128 hex characters')
    return {"proof": prove(key, nonce)}


# ---------------------------------------------------------------------------
# Signed calls: the key never travels
# ---------------------------------------------------------------------------

# The texts each signature is made over, before the request's own parts.
# yggshell's signal::clawdmeter holds the same bytes; one request vector and
# one response vector are pinned on both sides.
REQUEST_LABEL = b"clawdmeter host-api request v1\n"
RESPONSE_LABEL = b"clawdmeter host-api response v1\n"

# How long an issued nonce may be used, and how many may be outstanding. A
# client takes one per call, so a handful is in flight at most; the limit only
# bounds what a flood of challenges can make this daemon remember.
NONCE_SECONDS = 30
NONCE_LIMIT = 64

_SIGNED = re.compile(
    r"Clawdmeter-HMAC-SHA256 nonce=([0-9a-f]{64}), mac=([0-9a-f]{64})"
)


def request_mac(key: str, method: str, path: str, nonce: str, body: bytes) -> str:
    """The signature a client puts on one request, lowercase hex.

    HMAC-SHA256 over the label, the method, the path, the daemon's nonce and the
    SHA-256 of the body, each on its own line. The key is the bearer key, which
    then never crosses the wire: something else on the port learns a signature
    over a nonce this daemon will never accept again.
    """
    text = (REQUEST_LABEL + f"{method}\n{path}\n{nonce}\n".encode()
            + hashlib.sha256(body).hexdigest().encode())
    return hmac.new(key.encode(), text, hashlib.sha256).hexdigest()


def response_mac(key: str, nonce: str, status: int, body: bytes) -> str:
    """The signature this daemon puts on its answer to a signed request.

    Made over the same nonce, the HTTP status and the SHA-256 of the body, so a
    client believes a device state only from a holder of the key.
    """
    text = (RESPONSE_LABEL + f"{nonce}\n{status}\n".encode()
            + hashlib.sha256(body).hexdigest().encode())
    return hmac.new(key.encode(), text, hashlib.sha256).hexdigest()


class Nonces:
    """Nonces this daemon has handed out: each good once, for NONCE_SECONDS."""

    def __init__(self, clock=time.time) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._issued: dict[str, float] = {}   # nonce -> expiry; insertion order = age

    def issue(self) -> str:
        nonce = secrets.token_hex(32)
        with self._lock:
            self._issued[nonce] = self._clock() + NONCE_SECONDS
            while len(self._issued) > NONCE_LIMIT:
                del self._issued[next(iter(self._issued))]
        return nonce

    def take(self, nonce: str) -> bool:
        """True once for an issued, unexpired nonce; it is gone afterwards."""
        with self._lock:
            expiry = self._issued.pop(nonce, None)
        return expiry is not None and self._clock() < expiry


def challenge(nonces: Nonces) -> dict:
    return {"nonce": nonces.issue(), "ttl_s": NONCE_SECONDS}


# ---------------------------------------------------------------------------
# Key
# ---------------------------------------------------------------------------

def load_or_create_key(path: Path) -> str:
    """The bearer key clients present. Created once, kept in the user's profile.

    Only processes of this Windows user can read the file, which is the same
    boundary the Claude token itself sits behind.
    """
    try:
        key = path.read_text(encoding="utf-8").strip()
        if len(key) >= 32:
            return key
    except OSError:
        pass
    key = secrets.token_urlsafe(32)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(key + "\n", encoding="utf-8")
    return key


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _handler_for(state: HostState, key: str, log, nonces: Nonces):
    class Handler(BaseHTTPRequestHandler):
        server_version = "Clawdmeter"
        sys_version = ""

        def log_message(self, fmt, *args):   # stay out of stderr (pythonw)
            pass

        def _send(self, code: int, body: dict, signed_for: str | None = None) -> None:
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            if signed_for is not None:
                self.send_header("X-Clawdmeter-MAC", response_mac(key, signed_for, code, data))
            self.end_headers()
            self.wfile.write(data)

        def _raw(self) -> bytes:
            """The request body as sent, read once: a signature covers these bytes."""
            if not hasattr(self, "_raw_body"):
                length = int(self.headers.get("Content-Length") or 0)
                if length > 4096:
                    raise ApiError(413, "body too large")
                self._raw_body = self.rfile.read(length) if length else b""
            return self._raw_body

        def _authorize(self, method: str, path: str) -> str | None:
            """Who may call: the nonce of a valid signature, or None for the bearer key.

            A signed request whose nonce was issued, is fresh and is used here
            for the first time, with a MAC over exactly this method, path and
            body, is served and its answer signed over the same nonce. The nonce
            is spent before the MAC is checked, so a wrong guess burns it.
            Anything else signed is refused unsigned: an answer signed over a
            nonce this daemon did not accept would be a signing oracle.
            """
            got = self.headers.get("Authorization", "")
            if got.startswith("Clawdmeter-HMAC-SHA256"):
                m = _SIGNED.fullmatch(got)
                if not m:
                    raise ApiError(401, "malformed signature")
                nonce, mac = m.groups()
                if not nonces.take(nonce):
                    raise ApiError(401, "unknown or used nonce")
                want = request_mac(key, method, path, nonce, self._raw())
                if not hmac.compare_digest(mac.encode(), want.encode()):
                    raise ApiError(401, "bad signature")
                return nonce
            # Older clients still send the key itself; accepted until every
            # client signs (yggshell ADR-PROJ-011, amendment of 2026-11-21).
            if hmac.compare_digest(got.encode(), f"Bearer {key}".encode()):
                return None
            raise ApiError(401, "missing or wrong bearer key")

        def _body(self) -> dict:
            raw = self._raw()
            if not raw:
                return {}
            try:
                body = json.loads(raw)
            except (ValueError, UnicodeDecodeError):
                raise ApiError(400, "body is not JSON")
            if not isinstance(body, dict):
                raise ApiError(400, "body must be a JSON object")
            return body

        def _dispatch(self, method: str) -> None:
            path = self.path.split("?", 1)[0].rstrip("/")
            signed_for = None
            try:
                if method == "GET" and path == "/api/info":
                    return self._send(200, info())
                # No key: the whole point is to prove the daemon holds it
                # before a client sends it (see prove()).
                if method == "POST" and path == "/api/prove":
                    return self._send(200, prove_answer(key, self._body()))
                # No key: a nonce is worth nothing without the key to sign with.
                if method == "POST" and path == "/api/challenge":
                    return self._send(200, challenge(nonces))
                routes = {
                    ("GET", "/api/status"): lambda: state.status(),
                    ("POST", "/api/status"): lambda: state.claim(self._body()),
                    ("POST", "/api/keepalive"): lambda: state.keepalive(),
                    ("POST", "/api/release"): lambda: state.release(),
                }
                if (method, path) not in routes:
                    known = {p for _, p in routes} | {"/api/info", "/api/prove", "/api/challenge"}
                    if path in known:
                        raise ApiError(405, f"{method} not allowed on {path}")
                    raise ApiError(404, f"no such endpoint {path}")
                signed_for = self._authorize(method, path)
                result = routes[(method, path)]()
                if method == "POST" and path == "/api/status":
                    log(f"Host API: claim -> {result['anim'] or '(device)'}")
                self._send(200, result, signed_for)
            except ApiError as e:
                self._send(e.status, {"error": e.message}, signed_for)

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

    return Handler


class HostApiServer:
    """The HTTP listener, on a thread of its own. Loopback only."""

    def __init__(self, state: HostState, key: str, port: int, log) -> None:
        self._httpd = ThreadingHTTPServer(("127.0.0.1", port),
                                          _handler_for(state, key, log, Nonces()))
        self._httpd.daemon_threads = True
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(target=self._httpd.serve_forever,
                                        name="host-api", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()


# One per process: the tray restarts a crashed daemon loop without restarting
# the process, and a second bind on the same port would fail.
STATE = HostState()
_server: HostApiServer | None = None
_server_lock = threading.Lock()


def ensure_started(port: int, key_path: Path, log) -> HostApiServer | None:
    global _server
    with _server_lock:
        if _server is not None:
            return _server
        try:
            key = load_or_create_key(key_path)
            _server = HostApiServer(STATE, key, port, log)
        except OSError as e:
            log(f"Host API not started on 127.0.0.1:{port}: {e}")
            return None
        _server.start()
        log(f"Host API listening on http://127.0.0.1:{_server.port} (key: {key_path})")
        return _server
