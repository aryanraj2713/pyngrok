from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from pyngrok.cli import app
from pyngrok.engine import find_engine, parse_event, run_engine
from pyngrok.models import Session, endpoint

runner = CliRunner()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("8000", "127.0.0.1:8000"),
        ("localhost:42", "localhost:42"),
        ("[::1]:8080", "[::1]:8080"),
        (" 8080 ", "127.0.0.1:8080"),
    ],
)
def test_endpoint(value: str, expected: str) -> None:
    assert endpoint(value, default_host="127.0.0.1") == expected


@pytest.mark.parametrize(
    "value",
    [
        "0",
        "65536",
        "https://host:80",
        ":80",
        "::1:80",
        "host:abc",
        "host:１２",
        "host name:80",
        "[host]:80",
    ],
)
def test_invalid_endpoint(value: str) -> None:
    with pytest.raises(ValueError):
        endpoint(value, default_host="127.0.0.1")


def test_cli_validation() -> None:
    assert runner.invoke(app, ["tcp", "70000"]).exit_code == 2
    assert runner.invoke(app, ["tcp", "8000", "--public-port", "-1"]).exit_code == 2
    assert runner.invoke(app, ["relay", "--max-connections", "0"]).exit_code == 2


def test_keygen() -> None:
    first = runner.invoke(app, ["keygen"])
    second = runner.invoke(app, ["keygen"])
    assert first.exit_code == 0
    assert len(first.stdout.strip()) >= 32
    assert first.stdout != second.stdout


def test_preview_is_explicit_demo() -> None:
    result = runner.invoke(app, ["preview"])
    assert result.exit_code == 0
    assert "no tunnel running" in result.stdout


def test_session_rejects_bad_counters() -> None:
    session = Session(mode="tcp")
    session.update({"event": "connection_open"})
    session.update({"event": "connection_close", "bytes_up": -1, "bytes_down": "secret"})
    assert (session.active, session.total, session.bytes_up, session.bytes_down) == (0, 1, 0, 0)


@pytest.mark.parametrize("line", ["[]", "{}", '{"event": 1}', "not JSON", "x" * 65537])
def test_invalid_engine_events(line: str) -> None:
    with pytest.raises(ValueError):
        parse_event(line)


def test_engine_override_is_authoritative(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYNGROK_CORE", "/does/not/exist")
    with pytest.raises(ValueError, match="PYNGROK_CORE"):
        find_engine()


def test_real_child_process_events(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exercise the actual supervisor subprocess and stdout boundary, without network claims."""
    engine = tmp_path / "engine"
    engine.write_text(
        '#!/bin/sh\nprintf \'%s\\n\' \'{"event":"tunnel_ready",'
        '"public_address":"localhost:9999"}\'\n'
    )
    engine.chmod(0o700)
    monkeypatch.setenv("PYNGROK_CORE", str(engine))
    monkeypatch.setenv("PYNGROK_TOKEN", "test-only-0123456789")
    session = Session(mode="tcp")
    assert run_engine(["connect"], session, json_output=True) == 0
    assert session.public_address == "localhost:9999"
    assert json.loads(capsys.readouterr().out)["event"] == "tunnel_ready"


def test_missing_token_fails_before_launch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYNGROK_CORE", os.path.realpath("/bin/sh"))
    monkeypatch.delenv("PYNGROK_TOKEN", raising=False)
    with pytest.raises(ValueError, match="PYNGROK_TOKEN"):
        run_engine([], Session(mode="tcp"), json_output=True)
