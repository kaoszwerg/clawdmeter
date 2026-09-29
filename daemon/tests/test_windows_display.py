"""Display settings the Windows daemon adds to the payload (sleep, bar colour).

Run: python -m pytest daemon/tests/test_windows_display.py -q
"""
import pytest

from daemon import claude_usage_daemon_windows as d


@pytest.fixture
def config(tmp_path, monkeypatch):
    path = tmp_path / "config"
    monkeypatch.setattr(d, "CONFIG_FILE", path)
    return path


@pytest.mark.parametrize("text, expected", [
    ("", {}),
    ("sleep = 10\n", {"sl": 10}),
    ("sleep = off\n", {"sl": 0}),
    ("sleep = 0\n", {"sl": 0}),
    ("sleep = soon\n", {}),
    ("sleep = 99999\n", {}),
    ("bar_color = #3FA9F5\n", {"bc": "3fa9f5"}),
    ("bar_color = 3fa9f5  # blue\n", {"bc": "3fa9f5"}),
    ("bar_color = blue\n", {}),
    ("bar_color = #fff\n", {}),
])
def test_display_fields(config, text, expected):
    config.write_text(text)
    payload = {}
    d.add_display_fields(payload)
    assert payload == expected


def test_no_config_file_adds_nothing(config):
    payload = {}
    d.add_display_fields(payload)
    assert payload == {}
