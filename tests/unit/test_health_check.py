"""Unit tests (DATA-01): startup health-check failure surface, proven without
a terminal via the FakeMT5Client fixture.

Covers every connect_and_verify failure mode (initialize False,
terminal_info None, connected False, account_info None, symbol_select False,
expected_server mismatch) raising MT5ConnectionError with the last_error code
and an actionable remedy, the healthy path, the maxbars warning, and the
credential-scrub guarantee (threat T-1-05).
"""

from __future__ import annotations

import inspect
import logging
from types import SimpleNamespace

import pytest

from ai_trading import mt5_client
from ai_trading.collector import connect_and_verify
from ai_trading.mt5_client import MT5ConnectionError

# ---------------------------------------------------------------------------
# Healthy path
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_healthy_path_completes_without_raising(fake_mt5, make_cfg):
    connect_and_verify(make_cfg(), fake_mt5)  # must not raise
    assert fake_mt5.counts["initialize"] == 1
    assert fake_mt5.counts["terminal_info"] == 1
    assert fake_mt5.counts["account_info"] == 1


@pytest.mark.unit
def test_healthy_path_selects_every_configured_symbol(fake_mt5, make_cfg):
    cfg = make_cfg(symbols=("EURUSD", "GBPUSD", "USDJPY"))
    connect_and_verify(cfg, fake_mt5)
    selects = [call for name, call in fake_mt5.calls if name == "symbol_select"]
    assert selects == [(("EURUSD", True), {}), (("GBPUSD", True), {}), (("USDJPY", True), {})]
    assert fake_mt5.counts["symbol_select"] == 3


@pytest.mark.unit
def test_healthy_path_initializes_with_configured_path_and_timeout(fake_mt5, make_cfg):
    cfg = make_cfg(terminal_path=r"C:\FakeTerminals\terminal64.exe", init_timeout_ms=12345)
    connect_and_verify(cfg, fake_mt5)
    init_calls = [call for name, call in fake_mt5.calls if name == "initialize"]
    assert init_calls == [((), {"path": cfg.terminal_path, "timeout_ms": 12345})]


# ---------------------------------------------------------------------------
# Failure modes — every path raises MT5ConnectionError with code + remedy
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_initialize_false_raises_with_code_and_remedy(fake_mt5, make_cfg):
    fake_mt5.init_ok = False
    fake_mt5.error_code, fake_mt5.error_msg = -6, "Authorization failed"
    cfg = make_cfg(terminal_path=r"C:\FakeTerminals\terminal64.exe")
    with pytest.raises(MT5ConnectionError) as excinfo:
        connect_and_verify(cfg, fake_mt5)
    msg = str(excinfo.value)
    assert "[-6: Authorization failed]" in msg  # last_error code embedded
    assert "logged in" in msg  # actionable remedy
    assert str(cfg.terminal_path) in msg  # names the configured terminal path
    assert "-6" in msg  # the AUTH_FAILED explainer


@pytest.mark.unit
def test_terminal_info_none_raises(fake_mt5, make_cfg):
    fake_mt5.terminal_info_value = None
    with pytest.raises(MT5ConnectionError) as excinfo:
        connect_and_verify(make_cfg(), fake_mt5)
    msg = str(excinfo.value)
    assert "-6" in msg
    assert "log in to the trade server" in msg


@pytest.mark.unit
def test_connected_false_raises(fake_mt5, make_cfg):
    fake_mt5.connected = False
    with pytest.raises(MT5ConnectionError) as excinfo:
        connect_and_verify(make_cfg(), fake_mt5)
    msg = str(excinfo.value)
    assert "-6" in msg
    assert "log in to the trade server" in msg


@pytest.mark.unit
def test_account_none_raises_with_login_remedy(fake_mt5, make_cfg):
    fake_mt5.account = None
    with pytest.raises(MT5ConnectionError) as excinfo:
        connect_and_verify(make_cfg(), fake_mt5)
    msg = str(excinfo.value)
    assert "[-6: Authorization failed]" in msg
    assert "log in" in msg  # login remedy


@pytest.mark.unit
def test_expected_server_mismatch_names_both_servers(fake_mt5, make_cfg):
    fake_mt5.account = SimpleNamespace(server="OtherBroker-Live01", login=987654)
    cfg = make_cfg(expected_server="ICMarketsSC-Demo")
    with pytest.raises(MT5ConnectionError) as excinfo:
        connect_and_verify(cfg, fake_mt5)
    msg = str(excinfo.value)
    assert "OtherBroker-Live01" in msg  # actual server
    assert "ICMarketsSC-Demo" in msg  # configured server


@pytest.mark.unit
def test_empty_expected_server_skips_mismatch_check(fake_mt5, make_cfg):
    cfg = make_cfg(expected_server="")
    connect_and_verify(cfg, fake_mt5)  # no raise despite any server value


@pytest.mark.unit
def test_symbol_select_false_names_symbol_and_remedy(fake_mt5, make_cfg):
    fake_mt5.select_ok = False
    cfg = make_cfg(symbols=("EURUSD", "GBPUSD", "USDJPY"))
    with pytest.raises(MT5ConnectionError) as excinfo:
        connect_and_verify(cfg, fake_mt5)
    msg = str(excinfo.value)
    assert "symbol_select('EURUSD')" in msg  # first configured symbol fails
    assert "Market Watch" in msg  # suffix/remedy hint
    assert "-6" in msg
    # verification stops at the first failing symbol
    assert fake_mt5.counts["symbol_select"] == 1


@pytest.mark.unit
def test_connection_failures_are_never_bare_exceptions(fake_mt5, make_cfg):
    """Every scripted failure mode raises MT5ConnectionError specifically."""
    scenarios = [
        lambda f: setattr(f, "init_ok", False),
        lambda f: setattr(f, "terminal_info_value", None),
        lambda f: setattr(f, "connected", False),
        lambda f: setattr(f, "account", None),
        lambda f: setattr(f, "select_ok", False),
    ]
    for scenario in scenarios:
        fake = type(fake_mt5)()
        scenario(fake)
        with pytest.raises(MT5ConnectionError):
            connect_and_verify(make_cfg(), fake)


# ---------------------------------------------------------------------------
# maxbars warning (Pitfall 2)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_low_maxbars_warns_but_still_succeeds(fake_mt5, make_cfg, caplog):
    fake_mt5.maxbars = 5000
    cfg = make_cfg(min_maxbars=100000)
    with caplog.at_level(logging.WARNING, logger="ai_trading.collector"):
        connect_and_verify(cfg, fake_mt5)  # warning, not failure
    assert "5000" in caplog.text  # numeric maxbars value included
    assert "100000" in caplog.text  # configured threshold included
    assert "Unlimited" in caplog.text  # remedy included


@pytest.mark.unit
def test_adequate_maxbars_emits_no_warning(fake_mt5, make_cfg, caplog):
    with caplog.at_level(logging.WARNING, logger="ai_trading.collector"):
        connect_and_verify(make_cfg(), fake_mt5)
    assert "maxbars" not in caplog.text


# ---------------------------------------------------------------------------
# Credential hygiene (T-1-05 / ASVS V7)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_initialize_exposes_no_credential_parameters():
    """Structural guarantee: the adapter surface has no credential parameters,
    so nothing can leak them — terminal-saved credentials are the auth path."""
    params = inspect.signature(mt5_client.initialize).parameters
    for credential_name in ("login", "password", "server"):
        assert credential_name not in params


@pytest.mark.unit
def test_credentials_never_appear_in_raised_messages(fake_mt5, make_cfg):
    """Worst case: a credential value is handed to the client (the real
    package's initialize accepts login/password) — no raised message may
    contain it."""
    fake_mt5.init_ok = False
    fake_mt5.initialize(
        path=r"C:\FakeTerminals\terminal64.exe",
        login=987654,
        password="hunter2-fake-password",
    )
    with pytest.raises(MT5ConnectionError) as excinfo:
        connect_and_verify(make_cfg(), fake_mt5)
    assert "hunter2-fake-password" not in str(excinfo.value)
