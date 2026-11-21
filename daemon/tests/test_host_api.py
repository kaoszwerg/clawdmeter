"""Host API: claim rules, the firmware animation list, and the HTTP surface.

Run: python -m pytest daemon/tests/test_host_api.py -q
"""
import asyncio
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from daemon import host_api
from daemon.host_api import (
    ANIMATIONS, CLAIM_SECONDS, SIGNALS, ApiError, HostApiServer, HostState,
)

REPO = Path(__file__).resolve().parents[2]


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


# ---------------------------------------------------------------------------
# The contract with the firmware
# ---------------------------------------------------------------------------

def test_animation_list_matches_firmware():
    header = (REPO / "firmware" / "src" / "splash_animations.h").read_text(encoding="utf-8")
    names = re.findall(r'^\s*\{"([^"]+)", "[^"]*", \d+, splash_', header, re.M)
    assert tuple(names) == ANIMATIONS


def test_every_signal_maps_to_a_known_animation():
    for signal, anim in SIGNALS.items():
        assert anim == "" or anim in ANIMATIONS, signal
    assert set(SIGNALS) == {"off", "free", "away", "busy", "call", "focus"}


def test_firmware_field_fits():
    # UsageData.anim is char[24]: 23 characters + NUL.
    assert max(len(a) for a in ANIMATIONS) <= 23


# ---------------------------------------------------------------------------
# Claim rules
# ---------------------------------------------------------------------------

def test_device_leads_until_claimed():
    s = HostState(clock=Clock())
    assert s.wanted_anim() == ""
    st = s.status()
    assert st["source"] == "device" and st["hold_s"] == 0 and st["status"] is None


def test_signal_claim_maps_and_holds():
    clock = Clock()
    s = HostState(clock=clock)
    st = s.claim({"status": "busy"})
    assert st["source"] == "app"
    assert st["status"] == "busy"
    assert st["anim"] == "allow"
    assert st["hold_s"] == CLAIM_SECONDS
    assert s.wanted_anim() == "allow"


def test_anim_claim_is_verbatim():
    s = HostState(clock=Clock())
    st = s.claim({"anim": "dance bounce"})
    assert st["anim"] == "dance bounce" and st["status"] is None


def test_claim_lapses_after_claim_seconds():
    clock = Clock()
    s = HostState(clock=clock)
    s.claim({"status": "away"})
    clock.t += CLAIM_SECONDS - 1
    assert s.wanted_anim() == "work coding"
    clock.t += 1
    assert s.wanted_anim() == ""
    assert s.status()["source"] == "device"


def test_keepalive_extends_and_does_not_revive():
    clock = Clock()
    s = HostState(clock=clock)
    s.claim({"status": "away"})
    clock.t += 60
    assert s.keepalive()["hold_s"] == CLAIM_SECONDS
    clock.t += CLAIM_SECONDS
    st = s.keepalive()          # already lapsed: stays with the device
    assert st["source"] == "device" and st["hold_s"] == 0


def test_release_and_off_hand_back():
    s = HostState(clock=Clock())
    s.claim({"status": "busy"})
    assert s.release()["source"] == "device"
    s.claim({"status": "busy"})
    assert s.claim({"status": "off"})["source"] == "device"
    assert s.wanted_anim() == ""


@pytest.mark.parametrize("body", [
    {}, {"status": "busy", "anim": "done"}, {"status": "red"}, {"anim": "nope"},
])
def test_bad_claims_are_refused(body):
    with pytest.raises(ApiError) as e:
        HostState(clock=Clock()).claim(body)
    assert e.value.status == 400


def test_link_loss_forgets_device_facts_not_the_claim():
    s = HostState(clock=Clock())
    s.set_link(True, "44:1B:F6:83:F3:41")
    s.set_battery(80)
    s.set_written("allow")
    s.claim({"status": "busy"})
    s.set_link(False)
    st = s.status()
    assert st["connected"] is False
    assert st["battery"] is None and st["shown"] is None
    assert st["anim"] == "allow"       # delivered on the next connect


def test_never_paired_reads_as_absent_not_as_a_fault():
    s = HostState(clock=Clock())
    st = s.status()
    assert st["paired"] is None            # not looked yet
    s.set_paired(False)
    st = s.status()
    assert st["paired"] is False
    assert st["connected"] is False and st["address"] is None
    assert st["shown"] is None and st["battery"] is None
    assert st["usage"] is None and st["written_at"] is None
    assert st["error"] is None


def test_off_answers_exactly_like_release():
    a = HostState(clock=Clock())
    a.claim({"status": "busy"})
    b = HostState(clock=Clock())
    b.claim({"status": "busy"})
    assert a.claim({"status": "off"}) == b.release()
    assert a.status()["status"] is None and a.status()["anim"] == ""


def test_usage_is_reported_in_plain_names():
    s = HostState(clock=Clock(500.0))
    s.set_usage({"s": 6, "sr": 39, "w": 83, "wr": 1339, "st": "allowed", "acct": "pro"})
    assert s.status()["usage"] == {
        "session_pct": 6, "session_reset_min": 39, "weekly_pct": 83,
        "weekly_reset_min": 1339, "status": "allowed", "account": "pro",
        "updated_at": 500,
    }


def test_a_change_wakes_the_daemon_loop():
    async def run():
        s = HostState(clock=Clock())
        ev = asyncio.Event()
        s.attach(asyncio.get_running_loop(), ev)
        s.claim({"status": "busy"})
        await asyncio.wait_for(ev.wait(), 1.0)
        ev.clear()
        s.claim({"status": "busy"})       # same animation: no wake
        await asyncio.sleep(0.05)
        assert not ev.is_set()
        s.release()
        await asyncio.wait_for(ev.wait(), 1.0)
    asyncio.run(run())


def test_key_is_created_once(tmp_path):
    p = tmp_path / "sub" / "api-key"
    k1 = host_api.load_or_create_key(p)
    assert len(k1) >= 32
    assert host_api.load_or_create_key(p) == k1


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

@pytest.fixture
def server():
    state = HostState()
    srv = HostApiServer(state, "k" * 40, 0, lambda _m: None)
    srv.start()
    yield srv, state
    srv.stop()


def _call(srv, method, path, body=None, key="k" * 40):
    """One call, signed with `key` (no Authorization at all when `key` is None)."""
    if key is None:
        code, _, raw = _raw(srv, method, path, body)
    else:
        code, _, raw, _ = _signed(srv, method, path, body, key=key)
    return code, json.loads(raw)


def test_info_needs_no_key(server):
    srv, _ = server
    code, body = _call(srv, "GET", "/api/info", key=None)
    assert code == 200
    assert body["device"] == "clawdmeter" and body["api"] == 1
    assert body["animations"] == list(ANIMATIONS)


@pytest.mark.parametrize("key", [None, "wrong"])
def test_everything_else_needs_the_key(server, key):
    srv, _ = server
    assert _call(srv, "GET", "/api/status", key=key)[0] == 401
    assert _call(srv, "POST", "/api/status", {"status": "busy"}, key=key)[0] == 401


def test_claim_round_trip(server):
    srv, state = server
    code, body = _call(srv, "POST", "/api/status", {"status": "busy"})
    assert code == 200 and body["anim"] == "allow" and body["source"] == "app"
    assert state.wanted_anim() == "allow"
    assert _call(srv, "POST", "/api/keepalive")[1]["hold_s"] == CLAIM_SECONDS
    assert _call(srv, "POST", "/api/release")[1]["source"] == "device"


def test_errors_are_json(server):
    srv, _ = server
    assert _call(srv, "POST", "/api/status", {"status": "red"})[0] == 400
    assert _call(srv, "GET", "/api/nope")[0] == 404
    assert _call(srv, "GET", "/api/keepalive")[0] == 405


# ---------------------------------------------------------------------------
# The proof is gone: with no bearer key there is nothing left to prove
# ---------------------------------------------------------------------------

def test_the_proof_endpoint_is_gone(server):
    srv, _ = server
    assert _call(srv, "POST", "/api/prove", {"nonce": "ab" * 32}, key=None)[0] == 404
    assert "prove" not in _call(srv, "GET", "/api/info", key=None)[1]
    assert not hasattr(host_api, "prove")


# ---------------------------------------------------------------------------
# Signed calls: the key never travels
# ---------------------------------------------------------------------------

SHARED_NONCE = "00112233445566778899aabbccddeeff" * 2


def test_request_mac_matches_the_shared_vector():
    # Pinned in yggshell too
    # (src-tauri/src/signal/clawdmeter.rs::the_request_signature_is_the_one_the_daemon_checks).
    assert host_api.request_mac(
        "k3y-shared-vector", "POST", "/api/status", SHARED_NONCE, b'{"status":"busy"}',
    ) == "19525b77db9907afd094e4486757a1714bbc891384fbf7392e8d5bd65544071f"


def test_response_mac_matches_the_shared_vector():
    # Pinned in yggshell too
    # (src-tauri/src/signal/clawdmeter.rs::the_answer_signature_is_the_one_the_daemon_makes).
    assert host_api.response_mac(
        "k3y-shared-vector", SHARED_NONCE, 200, b'{"ok":true}',
    ) == "dc9096890455c018e415a8555472f2cb7f708f9543df1ddf2eccec7c07c1acf1"


def test_a_nonce_is_good_once_and_only_while_fresh():
    clock = Clock()
    nonces = host_api.Nonces(clock=clock)
    a, b = nonces.issue(), nonces.issue()
    assert re.fullmatch(r"[0-9a-f]{64}", a) and a != b
    assert nonces.take(a) is True
    assert nonces.take(a) is False            # single use
    clock.t += host_api.NONCE_SECONDS
    assert nonces.take(b) is False            # expired
    assert nonces.take("ab" * 32) is False    # never issued


def test_only_the_newest_nonces_are_kept():
    nonces = host_api.Nonces(clock=Clock())
    first = nonces.issue()
    rest = [nonces.issue() for _ in range(host_api.NONCE_LIMIT)]
    assert nonces.take(first) is False
    assert all(nonces.take(n) for n in rest)


def _raw(srv, method, path, body=None, headers=None):
    data = None if body is None else json.dumps(body, separators=(",", ":")).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{srv.port}{path}", method=method, data=data,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.headers, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


def _signed(srv, method, path, body=None, key="k" * 40, nonce=None, tamper=None):
    if nonce is None:
        code, _, raw = _raw(srv, "POST", "/api/challenge")
        assert code == 200
        nonce = json.loads(raw)["nonce"]
    data = b"" if body is None else json.dumps(body, separators=(",", ":")).encode()
    signed_method, signed_path, signed_data = method, path, data
    if tamper == "method":
        signed_method = "GET" if method == "POST" else "POST"
    if tamper == "path":
        signed_path = "/api/release"
    if tamper == "body":
        signed_data = data + b" "
    mac = host_api.request_mac(key, signed_method, signed_path, nonce, signed_data)
    code, headers, raw = _raw(srv, method, path, body, {
        "Authorization": f"Clawdmeter-HMAC-SHA256 nonce={nonce}, mac={mac}",
    })
    return code, headers, raw, nonce


def test_a_challenge_needs_no_key_and_info_says_signing_is_offered(server):
    srv, _ = server
    code, _, raw = _raw(srv, "POST", "/api/challenge")
    body = json.loads(raw)
    assert code == 200 and re.fullmatch(r"[0-9a-f]{64}", body["nonce"])
    assert body["ttl_s"] == host_api.NONCE_SECONDS
    assert _call(srv, "GET", "/api/info", key=None)[1]["sign"] is True
    assert _call(srv, "GET", "/api/challenge", key=None)[0] == 405


def test_a_signed_call_is_served_and_its_answer_is_signed(server):
    srv, state = server
    code, headers, raw, nonce = _signed(srv, "POST", "/api/status", {"status": "busy"})
    assert code == 200 and json.loads(raw)["anim"] == "allow"
    assert state.wanted_anim() == "allow"
    assert headers["X-Clawdmeter-MAC"] == host_api.response_mac("k" * 40, nonce, 200, raw)
    code, headers, raw, nonce = _signed(srv, "GET", "/api/status")
    assert code == 200
    assert headers["X-Clawdmeter-MAC"] == host_api.response_mac("k" * 40, nonce, 200, raw)


def test_a_signed_call_cannot_be_replayed(server):
    srv, _ = server
    _, _, _, nonce = _signed(srv, "POST", "/api/keepalive")
    code, headers, _, _ = _signed(srv, "POST", "/api/keepalive", nonce=nonce)
    assert code == 401 and "X-Clawdmeter-MAC" not in headers


@pytest.mark.parametrize("tamper", ["method", "path", "body"])
def test_a_signature_over_another_request_is_refused(server, tamper):
    srv, state = server
    code, headers, _, _ = _signed(srv, "POST", "/api/status", {"status": "busy"}, tamper=tamper)
    assert code == 401 and "X-Clawdmeter-MAC" not in headers
    assert state.wanted_anim() == ""


def test_a_signature_with_another_key_is_refused_and_burns_the_nonce(server):
    srv, _ = server
    code, _, _, nonce = _signed(srv, "POST", "/api/keepalive", key="w" * 40)
    assert code == 401
    assert _signed(srv, "POST", "/api/keepalive", nonce=nonce)[0] == 401


@pytest.mark.parametrize("header", [
    "Clawdmeter-HMAC-SHA256 nonce=ab, mac=cd",
    "Clawdmeter-HMAC-SHA256 mac=" + "ab" * 32,
    "Clawdmeter-HMAC-SHA256",
    "Bearer",
])
def test_a_malformed_signature_is_refused(server, header):
    srv, _ = server
    assert _raw(srv, "POST", "/api/keepalive", headers={"Authorization": header})[0] == 401


def test_the_bearer_key_is_refused_even_when_it_is_right(server):
    # Every client signs since yggshell 0.260.17; the key itself no longer opens anything,
    # so a program that learned it on the port can do nothing with it here either.
    srv, state = server
    for method, path, body in [("POST", "/api/keepalive", None),
                               ("POST", "/api/status", {"status": "busy"}),
                               ("GET", "/api/status", None)]:
        code, headers, _ = _raw(srv, method, path, body, {"Authorization": f"Bearer {'k' * 40}"})
        assert code == 401 and "X-Clawdmeter-MAC" not in headers
    assert state.wanted_anim() == ""


# ---------------------------------------------------------------------------
# Waking the panel
# ---------------------------------------------------------------------------

def test_busy_and_call_wake_once_other_signals_do_not():
    s = HostState(clock=Clock())
    s.claim({"status": "away"})
    assert s.take_wake() is False
    s.claim({"status": "busy"})
    assert s.take_wake() is True
    assert s.take_wake() is False          # one-shot
    s.claim({"status": "busy"})             # renewal, not a change
    assert s.take_wake() is False
    s.claim({"status": "call"})
    assert s.take_wake() is True
    s.claim({"anim": "allow"})              # raw anim never wakes
    assert s.take_wake() is False


# ---------------------------------------------------------------------------
# Clock and Content-Length at the edge
# ---------------------------------------------------------------------------

def test_nonces_run_on_a_monotonic_clock():
    # A wall-clock step (NTP, a manual change) must not expire or revive nonces.
    import inspect
    import time
    assert inspect.signature(host_api.Nonces).parameters["clock"].default is time.monotonic


def _raw_call(srv, head: bytes, timeout=3):
    """Send a hand-written request; urllib would fix a bad Content-Length itself."""
    import socket
    with socket.create_connection(("127.0.0.1", srv.port), timeout=timeout) as s:
        s.sendall(head)
        data = b""
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            data += chunk
    status = int(data.split(b" ", 2)[1])
    return status, json.loads(data.split(b"\r\n\r\n", 1)[1])


def _signed_head(srv, length: str) -> bytes:
    """A signed POST /api/status whose Content-Length is `length`.

    The body is read to check the signature, so a fresh nonce and a well-formed
    MAC are enough to reach the Content-Length check.
    """
    code, _, raw = _raw(srv, "POST", "/api/challenge")
    assert code == 200
    nonce = json.loads(raw)["nonce"]
    return (f"POST /api/status HTTP/1.1\r\nHost: x\r\n"
            f"Authorization: Clawdmeter-HMAC-SHA256 nonce={nonce}, mac={'ab' * 32}\r\n"
            f"Content-Type: application/json\r\nContent-Length: {length}\r\n"
            "Connection: close\r\n\r\n").encode()


@pytest.mark.parametrize("length", ["-1", "abc", "1e3", ""])
def test_a_bad_content_length_is_a_400_not_a_hang(server, length):
    srv, _ = server
    status, body = _raw_call(srv, _signed_head(srv, length))
    assert status == 400
    assert body == {"error": "bad Content-Length"}


@pytest.mark.parametrize("path, auth, code", [
    ("/api/prove", "", 404),
    ("/api/info", "", 405),
    ("/api/status", f"Authorization: Bearer {'k' * 40}\r\n", 401),
])
def test_an_error_is_answered_only_after_the_body_is_read(server, path, auth, code):
    # Measured on hugin 2026-11-21: an answer sent while the request body was
    # still unread made Windows abort the connection (WinError 10053), and the
    # client got no answer at all — now and then, in the full suite. So the
    # daemon reads the announced body (it is at most 4 KiB) before any error
    # answer. Shown deterministically: half a body gets no answer yet, the
    # rest gets the error.
    import socket
    srv, _ = server
    with socket.create_connection(("127.0.0.1", srv.port), timeout=3) as s:
        s.sendall((f"POST {path} HTTP/1.1\r\nHost: x\r\n{auth}"
                   "Content-Type: application/json\r\nContent-Length: 20\r\n"
                   "Connection: close\r\n\r\n0123456789").encode())
        s.settimeout(0.4)
        with pytest.raises(socket.timeout):
            s.recv(1)
        s.settimeout(3)
        s.sendall(b"0123456789")
        data = b""
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            data += chunk
    assert int(data.split(b" ", 2)[1]) == code


def test_a_body_over_4_kib_is_still_a_413(server):
    srv, _ = server
    status, _ = _raw_call(srv, _signed_head(srv, "4097"))
    assert status == 413
