"""Telegram alerts: sending, secrecy of the bot token, and that every kind
of alert (signals, intraday patterns, forming-setup watches) reaches it."""

from datetime import datetime, timezone

import pytest
import requests

from src.data.models import IntradayWatch, SetupType, Signal, SignalAction
from src.notifications import dispatcher, telegram
from src.scanner.intraday_patterns import IntradayPattern

TOKEN = "123456789:AAExampleExampleExampleExample_-xyz"
CHAT = "987654321"


class _Resp:
    def __init__(self, code=200, body=None):
        self.status_code = code
        self._body = body if body is not None else {"ok": code == 200}

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class _Post:
    """Records requests and answers from a queue (last answer repeats)."""

    def __init__(self, *answers):
        self.answers = list(answers) or [_Resp(200)]
        self.calls = []

    def __call__(self, url, json=None, timeout=None, **kw):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        a = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(a, Exception):
            raise a
        return a


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    monkeypatch.setattr(telegram.settings, "telegram_bot_token", TOKEN)
    monkeypatch.setattr(telegram.settings, "telegram_chat_id", CHAT)
    monkeypatch.setattr(telegram, "_state", {"sent": 0, "failed": 0, "last_ok_at": None,
                                             "last_attempt_at": None, "last_error": None})
    monkeypatch.setattr(telegram.time, "sleep", lambda s: None)
    # No Redis in tests: an in-memory duplicate guard instead.
    seen: dict[str, str] = {}
    monkeypatch.setattr(dispatcher, "_recent_sms_fingerprints", lambda: dict(seen))
    monkeypatch.setattr(dispatcher, "_record_sms_fingerprint", lambda fp: seen.__setitem__(fp, "now"))
    # No test may reach the network through another channel.
    monkeypatch.setattr(dispatcher, "send_email_sms", lambda *a, **k: False)
    monkeypatch.setattr(dispatcher, "send_sms", lambda *a, **k: False)
    monkeypatch.setattr(dispatcher, "_send_text_sms", lambda *a, **k: False)
    monkeypatch.setattr(dispatcher, "send_webhook", lambda *a, **k: False)
    monkeypatch.setattr(dispatcher.http_requests, "post", lambda *a, **k: _Resp(200))
    import src.data.redis_store as rs
    monkeypatch.setattr(rs, "get_push_tokens", lambda: {})
    monkeypatch.setattr(rs, "log_alert", lambda *a, **k: None)


def _post(monkeypatch, *answers) -> _Post:
    p = _Post(*answers)
    monkeypatch.setattr(telegram.requests, "post", p)
    return p


def _config(monkeypatch, **over):
    cfg = dispatcher.NotificationConfig(auto_alerts_enabled=True, min_confidence=0.6)
    for k, v in over.items():
        setattr(cfg, k, v)
    monkeypatch.setattr(dispatcher, "load_config", lambda: cfg)
    return cfg


def _signal(sym="NVDA", action=SignalAction.BUY, conf=0.72, setup=SetupType.BREAKOUT, reason="Range break on volume"):
    return Signal(symbol=sym, action=action, setup_type=setup, reason=reason, entry=123.45,
                  stop_loss=122.10, target=126.00, rr_ratio=1.9, confidence=conf,
                  timestamp=datetime(2026, 11, 11, 15, 0, tzinfo=timezone.utc))


def _pattern(sym="AMD"):
    return IntradayPattern(symbol=sym, pattern_type="breakout", action="BUY", trigger_price=250.5,
                           extreme_price=248.0, move_pct=1.2, recovery_pct=0.8, volume_confirmed=True,
                           detected_at=datetime(2026, 11, 11, 15, 0, tzinfo=timezone.utc))


def _watch(sym="TSM"):
    return IntradayWatch(symbol=sym, watch_type="box_forming", detail="tight box", upper=201.5, lower=200.0,
                         timestamp=datetime(2026, 11, 11, 15, 0, tzinfo=timezone.utc))


class TestSendText:
    def test_posts_to_the_bot_with_chat_and_text(self, monkeypatch):
        p = _post(monkeypatch)
        assert telegram.send_text("hello") is True
        call = p.calls[0]
        assert call["url"] == f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        assert call["json"]["chat_id"] == CHAT and call["json"]["text"] == "hello"
        assert "parse_mode" not in call["json"]          # plain text: no Markdown rejections
        assert call["timeout"]                           # never an unbounded wait
        assert telegram.status()["sent"] == 1 and telegram.status()["last_error"] is None

    @pytest.mark.parametrize("token,chat", [("", CHAT), (TOKEN, ""), ("", ""), ("   ", CHAT), (TOKEN, "  ")])
    def test_does_nothing_when_not_configured(self, monkeypatch, token, chat):
        monkeypatch.setattr(telegram.settings, "telegram_bot_token", token)
        monkeypatch.setattr(telegram.settings, "telegram_chat_id", chat)
        p = _post(monkeypatch)
        assert telegram.configured() is False
        assert telegram.send_text("hello") is False and p.calls == []

    @pytest.mark.parametrize("body", ["", "   ", "\n", None])
    def test_empty_message_is_not_sent(self, monkeypatch, body):
        p = _post(monkeypatch)
        assert telegram.send_text(body) is False and p.calls == []

    def test_long_message_is_cut_on_a_line_boundary(self, monkeypatch):
        p = _post(monkeypatch)
        body = "\n".join(f"line {i} " + "x" * 60 for i in range(200))
        assert telegram.send_text(body) is True
        sent = p.calls[0]["json"]["text"]
        assert len(sent) <= 4096 and sent.endswith("(more not shown)")
        assert all(line.startswith("line ") for line in sent.splitlines()[:-1])

    def test_long_message_without_line_breaks_is_still_cut(self, monkeypatch):
        p = _post(monkeypatch)
        assert telegram.send_text("x" * 10000) is True
        assert len(p.calls[0]["json"]["text"]) <= 4096

    @pytest.mark.parametrize("code,desc,expect", [
        (401, "Unauthorized", "TELEGRAM_BOT_TOKEN"),
        (404, "Not Found", "TELEGRAM_BOT_TOKEN"),
        (403, "Forbidden: bot was blocked by the user", "press Start"),
        (400, "Bad Request: chat not found", "TELEGRAM_CHAT_ID"),
    ])
    def test_refusals_are_explained_and_not_retried(self, monkeypatch, code, desc, expect):
        p = _post(monkeypatch, _Resp(code, {"ok": False, "description": desc}))
        assert telegram.send_text("hello") is False
        assert len(p.calls) == 1
        err = telegram.status()["last_error"]
        assert f"HTTP {code}" in err and expect in err
        assert telegram.status()["failed"] == 1

    def test_server_error_is_retried_once(self, monkeypatch):
        p = _post(monkeypatch, _Resp(502, ValueError("not json")), _Resp(200))
        assert telegram.send_text("hello") is True
        assert len(p.calls) == 2 and telegram.status()["failed"] == 0

    def test_network_error_is_retried_once_then_reported(self, monkeypatch):
        p = _post(monkeypatch, requests.ConnectionError("down"))
        assert telegram.send_text("hello") is False
        assert len(p.calls) == 2
        assert "ConnectionError" in telegram.status()["last_error"]

    def test_short_rate_limit_waits_as_told_then_retries(self, monkeypatch):
        waits = []
        monkeypatch.setattr(telegram.time, "sleep", waits.append)
        limited = _Resp(429, {"ok": False, "description": "Too Many Requests", "parameters": {"retry_after": 3}})
        p = _post(monkeypatch, limited, _Resp(200))
        assert telegram.send_text("hello") is True
        assert waits == [3.0] and len(p.calls) == 2

    def test_long_rate_limit_gives_up_without_sleeping(self, monkeypatch):
        waits = []
        monkeypatch.setattr(telegram.time, "sleep", waits.append)
        limited = _Resp(429, {"ok": False, "description": "Too Many Requests", "parameters": {"retry_after": 600}})
        p = _post(monkeypatch, limited)
        assert telegram.send_text("hello") is False
        assert waits == [] and len(p.calls) == 1


class TestTokenNeverLeaks:
    def _leaky(self):
        # requests quotes the URL, token included, in its error text.
        return requests.ConnectionError(
            f"HTTPSConnectionPool(host='api.telegram.org', port=443): Max retries exceeded "
            f"with url: /bot{TOKEN}/sendMessage (Caused by NewConnectionError('unreachable'))")

    def test_not_in_status_after_a_network_error(self, monkeypatch):
        _post(monkeypatch, self._leaky())
        telegram.send_text("hello")
        s = telegram.status()
        assert s["last_error"] and "[token]" in s["last_error"]
        assert TOKEN not in str(s) and CHAT not in str(s)

    def test_not_in_logs(self, monkeypatch, mse_logs):
        _post(monkeypatch, self._leaky())
        telegram.send_text("hello")
        dispatcher._send_telegram("signals", "body")
        assert "Telegram alert failed" in mse_logs.text           # the log was really captured
        assert TOKEN not in mse_logs.text and "AAExample" not in mse_logs.text

    def test_redacts_a_token_that_is_not_the_configured_one(self):
        other = "55555555:BBsomeOtherTokenValue_0123456789"
        out = telegram.redact(f"url: /bot{other}/sendMessage and /bot{TOKEN}/x")
        assert other not in out and TOKEN not in out and out.count("[token]") == 2

    def test_status_reports_setup_without_values(self, monkeypatch):
        s = telegram.status()
        assert s["configured"] is True and s["has_token"] is True and s["has_chat_id"] is True
        monkeypatch.setattr(telegram.settings, "telegram_chat_id", "")
        s = telegram.status()
        assert s["configured"] is False and s["has_token"] is True and s["has_chat_id"] is False

    def test_old_helper_redacts_too(self, monkeypatch, mse_logs):
        from src.notifications import channels

        def boom(*a, **k):
            raise self._leaky()

        monkeypatch.setattr(channels.requests, "post", boom)
        assert channels.send_telegram(TOKEN, CHAT, "hi") is False
        assert "Telegram send failed" in mse_logs.text            # the log was really captured
        assert TOKEN not in mse_logs.text

    def test_notification_config_has_no_telegram_secret_fields(self):
        # The saved config is served by a public endpoint.
        assert not any("telegram" in k and ("token" in k or "chat" in k)
                       for k in dispatcher.NotificationConfig().to_dict())


class TestFormat:
    def test_signal_body_carries_the_levels(self):
        body = dispatcher._format_telegram_signals([_signal()])
        assert body.splitlines()[0] == "MSE Alert"
        assert "BUY NVDA  breakout  72%" in body
        assert "entry $123.45 | stop $122.10 | target $126.00 | R:R 1.9" in body
        assert "Range break on volume" in body

    def test_exit_signal_without_levels_is_labelled_not_shown_as_zeros(self):
        # Seen in the first real Telegram alert on 2026-11-11:
        # "SELL NOC ... stop $0.00 | target $0.00 | R:R 0.0".
        exit_sig = Signal(symbol="NOC", action=SignalAction.SELL, setup_type=SetupType.EMA_CROSSOVER,
                          reason="Price dropped below ATR trailing stop", entry=544.46,
                          stop_loss=0.0, target=0.0, rr_ratio=0.0, confidence=0.75,
                          timestamp=datetime(2026, 11, 11, 15, 0, tzinfo=timezone.utc))
        body = dispatcher._format_telegram_signals([exit_sig, _signal()])
        assert "$0.00" not in body and "R:R 0.0" not in body
        assert "SELL NOC  ema crossover  75%  (exit or warning, no trade levels)" in body
        assert "price $544.46" in body
        assert "entry $123.45 | stop $122.10 | target $126.00 | R:R 1.9" in body   # trade keeps its levels

    @pytest.mark.parametrize("stop,target,rr", [(0.0, 126.0, 1.9), (122.1, 0.0, 1.9), (122.1, 126.0, 0.0)])
    def test_any_missing_level_counts_as_no_levels(self, stop, target, rr):
        s = _signal()
        s.stop_loss, s.target, s.rr_ratio = stop, target, rr
        body = dispatcher._format_telegram_signals([s])
        assert "no trade levels" in body and "$0.00" not in body

    def test_delay_label_is_in_the_header(self):
        with dispatcher.alert_label(" (14m delayed)"):
            body = dispatcher._format_telegram_signals([_signal()])
        assert body.splitlines()[0] == "MSE Alert (14m delayed)"

    def test_empty_input_gives_empty_body(self):
        assert dispatcher._format_telegram_signals([]) == ""

    def test_same_symbol_and_action_appears_once_highest_confidence(self):
        body = dispatcher._format_telegram_signals([
            _signal(conf=0.61, setup=SetupType.EMA_CROSSOVER), _signal(conf=0.90), _signal(conf=0.70)])
        assert body.count("NVDA") == 1 and "90%" in body

    def test_order_is_by_confidence_whatever_the_input_order(self):
        sigs = [_signal("AAA", conf=0.61), _signal("CCC", conf=0.95), _signal("BBB", conf=0.80)]
        forward = dispatcher._format_telegram_signals(sigs)
        backward = dispatcher._format_telegram_signals(list(reversed(sigs)))
        assert forward == backward
        assert forward.index("CCC") < forward.index("BBB") < forward.index("AAA")

    def test_more_than_the_limit_is_summarised(self):
        sigs = [_signal(f"S{chr(65 + i)}", conf=0.6 + i / 100) for i in range(13)]
        body = dispatcher._format_telegram_signals(sigs)
        assert body.count("entry $") == 10 and body.endswith("and 3 more")

    def test_watch_body_is_not_capped_at_sms_length_for_telegram(self):
        watches = [_watch(f"W{chr(65 + i)}") for i in range(12)]
        assert dispatcher._format_watch_body(watches).count("box") < 12
        assert dispatcher._format_watch_body(watches, max_chars=3500).count("box") == 12


class TestDispatch:
    def test_signals_go_to_telegram(self, monkeypatch):
        _config(monkeypatch)
        p = _post(monkeypatch)
        r = dispatcher.dispatch_alerts([_signal()])
        assert r["telegram"] is True and len(p.calls) == 1
        assert "BUY NVDA" in p.calls[0]["json"]["text"]

    def test_intraday_patterns_go_to_telegram(self, monkeypatch):
        _config(monkeypatch)
        p = _post(monkeypatch)
        r = dispatcher.dispatch_intraday_patterns([_pattern()])
        assert r["telegram"] is True and "AMD" in p.calls[0]["json"]["text"]

    def test_watches_go_to_telegram(self, monkeypatch):
        _config(monkeypatch)
        p = _post(monkeypatch)
        r = dispatcher.dispatch_intraday_watches([_watch()])
        assert r["telegram"] is True and "TSM box 200.00-201.50" in p.calls[0]["json"]["text"]

    def test_needs_no_phone_number_or_sms_consent(self, monkeypatch):
        _config(monkeypatch, sms_to="", sms_consent=False)
        _post(monkeypatch)
        assert dispatcher.dispatch_alerts([_signal()])["telegram"] is True
        assert dispatcher.dispatch_intraday_patterns([_pattern()])["telegram"] is True
        assert dispatcher.dispatch_intraday_watches([_watch()])["telegram"] is True

    def test_nothing_is_sent_when_alerts_are_switched_off(self, monkeypatch):
        _config(monkeypatch, auto_alerts_enabled=False)
        p = _post(monkeypatch)
        assert dispatcher.dispatch_alerts([_signal()])["telegram"] is False
        assert dispatcher.dispatch_intraday_patterns([_pattern()])["telegram"] is False
        assert dispatcher.dispatch_intraday_watches([_watch()])["telegram"] is False
        assert p.calls == []

    def test_signals_below_the_confidence_floor_are_not_sent(self, monkeypatch):
        _config(monkeypatch, min_confidence=0.8)
        p = _post(monkeypatch)
        assert dispatcher.dispatch_alerts([_signal(conf=0.7)])["telegram"] is False
        assert p.calls == []

    @pytest.mark.parametrize("fn", ["dispatch_alerts", "dispatch_intraday_patterns", "dispatch_intraday_watches"])
    def test_empty_input_sends_nothing(self, monkeypatch, fn):
        _config(monkeypatch)
        p = _post(monkeypatch)
        assert getattr(dispatcher, fn)([]).get("telegram") is False
        assert p.calls == []

    def test_not_configured_reports_false_and_other_channels_still_run(self, monkeypatch):
        monkeypatch.setattr(telegram.settings, "telegram_bot_token", "")
        _config(monkeypatch, sms_to="5550001111", sms_consent=True, sms_carrier="tmobile")
        monkeypatch.setattr(dispatcher, "send_email_sms", lambda *a, **k: True)
        p = _post(monkeypatch)
        r = dispatcher.dispatch_alerts([_signal()])
        assert r["telegram"] is False and r["sms"] is True and p.calls == []

    def test_identical_alert_is_not_repeated_within_the_window(self, monkeypatch):
        _config(monkeypatch)
        p = _post(monkeypatch)
        assert dispatcher.dispatch_alerts([_signal()])["telegram"] is True
        assert dispatcher.dispatch_alerts([_signal()])["telegram"] is False
        assert len(p.calls) == 1

    def test_more_than_five_patterns_all_reach_telegram(self, monkeypatch):
        # Found in review: Telegram reused the SMS cap of 5, and the loop marks
        # every pattern seen, so patterns 6 and later were never sent.
        _config(monkeypatch)
        p = _post(monkeypatch)
        pats = [_pattern(f"P{chr(65 + i)}") for i in range(8)]
        assert dispatcher.dispatch_intraday_patterns(pats)["telegram"] is True
        text = p.calls[0]["json"]["text"]
        assert all(f"P{chr(65 + i)} " in text for i in range(8))
        assert "more" not in text

    def test_patterns_past_the_telegram_limit_are_counted_not_dropped_silently(self):
        pats = [_pattern(f"S{i:02d}") for i in range(35)]
        body = dispatcher._format_intraday_body(pats, limit=30, show_more=True)
        assert body.count("$250.50") == 30 and body.endswith("and 5 more")

    def test_sms_pattern_body_is_unchanged(self):
        pats = [_pattern(f"P{chr(65 + i)}") for i in range(8)]
        body = dispatcher._format_intraday_body(pats)
        assert len(body.splitlines()) == 6 and "more" not in body

    def test_telegram_failure_does_not_stop_the_other_channels(self, monkeypatch):
        _config(monkeypatch, sms_to="5550001111", sms_consent=True, sms_carrier="tmobile")
        monkeypatch.setattr(dispatcher, "send_email_sms", lambda *a, **k: True)

        def boom(body):
            raise RuntimeError("unexpected")

        monkeypatch.setattr(telegram, "send_text", boom)
        r = dispatcher.dispatch_alerts([_signal()])
        assert r["telegram"] is False and r["sms"] is True

    def test_telegram_is_sent_before_the_slow_sms_attempt(self, monkeypatch):
        _config(monkeypatch, sms_to="5550001111", sms_consent=True, sms_carrier="tmobile")
        order = []
        monkeypatch.setattr(telegram, "send_text", lambda body: order.append("telegram") or True)
        monkeypatch.setattr(dispatcher, "send_email_sms", lambda *a, **k: order.append("sms") or False)
        dispatcher.dispatch_alerts([_signal()])
        assert order == ["telegram", "sms"]


class TestRetryQueue:
    """The scan loops mark an alert as seen whether or not it was delivered,
    so a failed Telegram send must be kept and retried, not lost."""

    DOWN = _Resp(503, {"ok": False, "description": "Service Unavailable"})

    def test_failed_send_is_queued_and_delivered_on_retry(self, monkeypatch):
        _config(monkeypatch)
        _post(monkeypatch, self.DOWN)
        assert dispatcher.dispatch_alerts([_signal()])["telegram"] is False
        assert dispatcher.telegram_pending() == 1
        p = _post(monkeypatch)
        assert dispatcher.retry_failed_telegram() == 1
        assert dispatcher.telegram_pending() == 0
        text = p.calls[0]["json"]["text"]
        assert "BUY NVDA" in text and "late: first attempt at" in text and "ET failed" in text

    def test_delivered_retry_counts_for_the_duplicate_guard(self, monkeypatch):
        _config(monkeypatch)
        _post(monkeypatch, self.DOWN)
        dispatcher.dispatch_alerts([_signal()])
        _post(monkeypatch)
        dispatcher.retry_failed_telegram()
        p = _post(monkeypatch)
        assert dispatcher.dispatch_alerts([_signal()])["telegram"] is False   # already delivered
        assert p.calls == []

    def test_every_alert_kind_is_queued(self, monkeypatch):
        _config(monkeypatch)
        _post(monkeypatch, self.DOWN)
        dispatcher.dispatch_alerts([_signal()])
        dispatcher.dispatch_intraday_patterns([_pattern()])
        dispatcher.dispatch_intraday_watches([_watch()])
        assert dispatcher.telegram_pending() == 3

    def test_outage_costs_one_request_per_retry_not_one_per_alert(self, monkeypatch):
        _config(monkeypatch)
        _post(monkeypatch, self.DOWN)
        for sym in ("AAA", "BBB", "CCC"):
            dispatcher.dispatch_alerts([_signal(sym)])
        p = _post(monkeypatch, self.DOWN)
        assert dispatcher.retry_failed_telegram() == 0
        assert len(p.calls) == 2                      # one send_text: first try plus its one retry
        assert dispatcher.telegram_pending() == 3

    def test_retry_is_oldest_first(self, monkeypatch):
        _config(monkeypatch)
        _post(monkeypatch, self.DOWN)
        for sym in ("AAA", "BBB", "CCC"):
            dispatcher.dispatch_alerts([_signal(sym)])
        p = _post(monkeypatch)
        assert dispatcher.retry_failed_telegram() == 3
        firsts = [c["json"]["text"] for c in p.calls]
        assert ["AAA" in firsts[0], "BBB" in firsts[1], "CCC" in firsts[2]] == [True, True, True]

    def test_partial_recovery_keeps_the_rest(self, monkeypatch):
        _config(monkeypatch)
        _post(monkeypatch, self.DOWN)
        for sym in ("AAA", "BBB"):
            dispatcher.dispatch_alerts([_signal(sym)])
        _post(monkeypatch, _Resp(200), self.DOWN)     # first delivered, then down again
        assert dispatcher.retry_failed_telegram() == 1
        assert dispatcher.telegram_pending() == 1

    def test_alerts_older_than_the_limit_are_dropped_unsent(self, monkeypatch):
        _config(monkeypatch)
        _post(monkeypatch, self.DOWN)
        dispatcher.dispatch_alerts([_signal()])
        p = _post(monkeypatch)
        later = __import__("time").time() + dispatcher._TG_PENDING_MAX_AGE + 1
        assert dispatcher.retry_failed_telegram(now=later) == 0
        assert p.calls == [] and dispatcher.telegram_pending() == 0

    def test_queue_is_capped_and_keeps_the_newest(self, monkeypatch):
        _config(monkeypatch)
        _post(monkeypatch, self.DOWN)
        monkeypatch.setattr(dispatcher, "_TG_PENDING_MAX", 3)
        for sym in ("AAA", "BBB", "CCC", "DDD", "EEE"):
            dispatcher.dispatch_alerts([_signal(sym)])
        assert dispatcher.telegram_pending() == 3
        assert [("CCC" in i["body"], "EEE" in i["body"]) for i in (dispatcher._tg_pending[0], dispatcher._tg_pending[-1])] \
            == [(True, False), (False, True)]

    def test_same_failed_alert_is_queued_once(self, monkeypatch):
        _config(monkeypatch)
        _post(monkeypatch, self.DOWN)
        dispatcher.dispatch_alerts([_signal()])
        dispatcher.dispatch_alerts([_signal()])
        assert dispatcher.telegram_pending() == 1

    def test_nothing_is_queued_when_telegram_is_not_set_up(self, monkeypatch):
        monkeypatch.setattr(telegram.settings, "telegram_bot_token", "")
        _config(monkeypatch)
        p = _post(monkeypatch)
        dispatcher.dispatch_alerts([_signal()])
        assert dispatcher.telegram_pending() == 0 and p.calls == []
        assert dispatcher.retry_failed_telegram() == 0

    def test_suppressed_duplicate_is_not_queued(self, monkeypatch):
        _config(monkeypatch)
        _post(monkeypatch)
        dispatcher.dispatch_alerts([_signal()])
        _post(monkeypatch, self.DOWN)
        dispatcher.dispatch_alerts([_signal()])       # suppressed before any send
        assert dispatcher.telegram_pending() == 0

    def test_empty_queue_sends_nothing(self, monkeypatch):
        p = _post(monkeypatch)
        assert dispatcher.retry_failed_telegram() == 0 and p.calls == []

    def test_retry_never_raises(self, monkeypatch):
        _config(monkeypatch)
        _post(monkeypatch, self.DOWN)
        dispatcher.dispatch_alerts([_signal()])

        def boom(body):
            raise RuntimeError("unexpected")

        monkeypatch.setattr(telegram, "send_text", boom)
        assert dispatcher.retry_failed_telegram() == 0
        assert dispatcher.telegram_pending() == 1

    def test_intraday_loop_retries_every_cycle_even_outside_market_hours(self):
        import inspect
        from src import main
        src = inspect.getsource(main._intraday_scan_loop)
        assert "retry_failed_telegram()" in src
        assert src.index("retry_failed_telegram()") < src.index("if not _is_market_hours_et()")


class TestSmtpTimeout:
    def test_every_mail_connection_has_a_timeout(self):
        # Found in production: a blocked mail port held the scan loop for
        # over two minutes per alert because the connection had no timeout.
        import inspect
        import re
        from src.notifications import channels
        for module in (dispatcher, channels):
            calls = re.findall(r"smtplib\.SMTP_SSL\(([^)]*)\)", inspect.getsource(module))
            assert calls, module.__name__
            assert all("timeout=" in c for c in calls), module.__name__


class TestRoutes:
    @pytest.fixture
    def client(self, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from src.api import routes
        monkeypatch.setattr(routes, "_telegram_test_at", 0.0)
        app = FastAPI()
        app.include_router(routes.router)
        return TestClient(app)

    def test_status_shows_no_secret(self, client):
        r = client.get("/notifications/telegram/status")
        assert r.status_code == 200 and r.json()["configured"] is True
        assert TOKEN not in r.text and CHAT not in r.text

    def test_status_reports_alerts_waiting_for_retry(self, client, monkeypatch):
        _config(monkeypatch)
        _post(monkeypatch, _Resp(503, {"ok": False}))
        dispatcher.dispatch_alerts([_signal()])
        assert client.get("/notifications/telegram/status").json()["pending_retry"] == 1

    def test_simultaneous_test_requests_send_once(self, monkeypatch):
        # Found in review: the once-a-minute check was not atomic, and sync
        # routes run on a thread pool.
        import threading
        from src.api import routes
        monkeypatch.setattr(routes, "_telegram_test_at", 0.0)
        sent = []

        def slow_send(body):
            sent.append(body)
            __import__("time").sleep(0.05)
            return True

        monkeypatch.setattr(telegram, "send_text", slow_send)
        gate = threading.Barrier(8)
        answers = []

        def hit():
            gate.wait()
            answers.append(routes.telegram_test()["status"])

        threads = [threading.Thread(target=hit) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(sent) == 1
        assert sorted(answers) == ["sent"] + ["wait"] * 7

    def test_test_message_is_sent_once_then_rate_limited(self, client, monkeypatch):
        p = _post(monkeypatch)
        assert client.post("/notifications/telegram/test").json()["status"] == "sent"
        assert client.post("/notifications/telegram/test").json()["status"] == "wait"
        assert len(p.calls) == 1
        assert p.calls[0]["json"]["chat_id"] == CHAT

    def test_caller_cannot_choose_text_or_destination(self, client, monkeypatch):
        p = _post(monkeypatch)
        client.post("/notifications/telegram/test?chat_id=111&message=spam&text=spam")
        assert p.calls[0]["json"]["chat_id"] == CHAT
        assert "spam" not in p.calls[0]["json"]["text"]

    def test_not_configured_is_reported(self, client, monkeypatch):
        monkeypatch.setattr(telegram.settings, "telegram_bot_token", "")
        p = _post(monkeypatch)
        assert client.post("/notifications/telegram/test").json()["status"] == "not_configured"
        assert p.calls == []

    def test_failure_message_has_no_token(self, client, monkeypatch):
        _post(monkeypatch, requests.ConnectionError(f"url: /bot{TOKEN}/sendMessage"))
        r = client.post("/notifications/telegram/test")
        assert r.json()["status"] == "error" and TOKEN not in r.text


class TestSettings:
    def test_keys_are_declared_and_blank_by_default(self):
        from config.settings import Settings
        for key in ("telegram_bot_token", "telegram_chat_id"):
            assert Settings.model_fields[key].default == ""
