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
    req = urllib.request.Request(
        f"http://127.0.0.1:{srv.port}{path}", method=method,
        data=None if body is None else json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {key}"} if key else {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


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
