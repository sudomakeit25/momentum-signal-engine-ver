"""The scheduled GitHub workflow that wakes the sleeping backend.

Runs the workflow's real step script with `date` and `curl` replaced by
stand-ins, so the New York time gate is checked without touching the
network. The window must match the app's own keep-alive window."""

import os
import pathlib
import shutil
import subprocess
import textwrap

import pytest

WORKFLOW = pathlib.Path(__file__).resolve().parent.parent / ".github" / "workflows" / "wake.yml"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")


def _text() -> str:
    return WORKFLOW.read_text()


def _step_script() -> str:
    """The body of the step's `run: |` block."""
    lines = _text().splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == "run: |")
    indent = len(lines[start]) - len(lines[start].lstrip())
    body = []
    for line in lines[start + 1:]:
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            break
        body.append(line)
    return textwrap.dedent("\n".join(body))


def _run(tmp_path, hhmm: str, dow: str, trigger: str = "schedule", curl_exit: int = 0):
    fake_date = tmp_path / "date"
    fake_date.write_text(
        '#!/bin/sh\ncase "$1" in +%H%M) echo "$FAKE_HHMM";; +%u) echo "$FAKE_DOW";; esac\n')
    fake_curl = tmp_path / "curl"
    fake_curl.write_text(f'#!/bin/sh\necho "CURL_CALLED $@"\nexit {curl_exit}\n')
    for f in (fake_date, fake_curl):
        f.chmod(0o755)
    env = dict(os.environ, PATH=f"{tmp_path}:{os.environ['PATH']}", FAKE_HHMM=hhmm, FAKE_DOW=dow,
               GITHUB_EVENT_NAME=trigger, BACKEND_URL="https://backend.example/health")
    # GitHub runs a step as `bash -e`.
    return subprocess.run(["bash", "-e", "-c", _step_script()], env=env,
                          capture_output=True, text=True, timeout=30)


@pytest.mark.parametrize("hhmm,dow,expect", [
    ("0354", "2", False),   # just before the window
    ("0355", "2", True),    # first minute
    ("0400", "2", True),
    ("0809", "3", True),    # leading zero with 8 or 9 is not valid octal
    ("0859", "3", True),
    ("0930", "1", True),    # Monday
    ("1545", "5", True),    # Friday, the auto-trader close
    ("1610", "5", True),    # last minute
    ("1611", "5", False),   # just after
    ("2337", "4", False),   # evening
    ("0007", "2", False),   # just after midnight
    ("1000", "6", False),   # Saturday
    ("1000", "7", False),   # Sunday
])
def test_scheduled_run_requests_only_inside_the_window(tmp_path, hhmm, dow, expect):
    p = _run(tmp_path, hhmm, dow)
    assert p.returncode == 0, p.stderr
    assert ("CURL_CALLED" in p.stdout) is expect


def test_manual_run_always_requests(tmp_path):
    p = _run(tmp_path, "2300", "6", trigger="workflow_dispatch")
    assert p.returncode == 0 and "CURL_CALLED" in p.stdout


def test_request_goes_to_the_configured_address_with_a_time_limit(tmp_path):
    p = _run(tmp_path, "1000", "2")
    assert "https://backend.example/health" in p.stdout
    assert "--max-time" in p.stdout and "--retry" in p.stdout and "--fail" in p.stdout


def test_failed_request_fails_the_run(tmp_path):
    # A backend that will not wake must show as a red run, not a green one.
    p = _run(tmp_path, "1000", "2", curl_exit=22)
    assert p.returncode != 0


def test_schedule_covers_the_window_in_winter_and_summer():
    text = _text()
    cron = next(line.split('"')[1] for line in text.splitlines() if "cron:" in line)
    minutes, hours, dom, month, dow = cron.split()
    assert (dom, month, dow) == ("*", "*", "1-5")
    first, last = (int(h) for h in hours.split("-"))
    # 04:00 New York is 08:00 UTC in summer; 16:00 is 21:00 UTC in winter.
    assert first <= 8 and last >= 21
    # At least two runs an hour, so a restart is noticed within the half hour.
    assert len(minutes.split(",")) >= 2


def test_gate_is_no_wider_than_the_apps_own_window():
    # The app holds the service awake from 04:00 to 16:15; waking it outside
    # that would only burn free hours.
    from src import keepalive as ka
    assert ka.DEFAULT_START.strftime("%H%M") == "0400"
    assert ka.DEFAULT_END.strftime("%H%M") >= "1610"


def test_workflow_holds_no_token_permissions():
    assert "permissions: {}" in _text()
    assert "workflow_dispatch:" in _text()
