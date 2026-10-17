"""Supervise the native engine without putting Python on the data path."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from rich.console import Console
from rich.live import Live

from pyngrok.models import Session
from pyngrok.ui import dashboard

MAX_EVENT_BYTES = 65_536


def find_engine() -> Path:
    configured = os.environ.get("PYNGROK_CORE")
    if configured:
        candidate = Path(configured).expanduser()
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate.resolve()
        raise ValueError("PYNGROK_CORE must point to an executable pyngrok-core binary")
    if getattr(sys, "frozen", False):
        bundled = Path(sys.executable).resolve().parent / "pyngrok-core"
        if bundled.is_file() and os.access(bundled, os.X_OK):
            return bundled
        raise ValueError("Bundled Rust engine is missing; reinstall pyngrok")
    installed = shutil.which("pyngrok-core")
    if installed:
        return Path(installed)
    # Source checkout convenience; installed wheels use PATH or PYNGROK_CORE.
    checkout = Path(__file__).resolve().parents[2]
    for profile in ("release", "debug"):
        candidate = checkout / "crates" / "pyngrok-core" / "target" / profile / "pyngrok-core"
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    raise ValueError(
        "Rust engine not found. Run: cargo build --release "
        "--manifest-path crates/pyngrok-core/Cargo.toml; "
        "or set PYNGROK_CORE to an installed binary."
    )


def parse_event(line: str) -> dict[str, object]:
    if len(line.encode("utf-8")) > MAX_EVENT_BYTES:
        raise ValueError("Native engine event exceeds 64 KiB")
    value: object = json.loads(line)
    if not isinstance(value, dict) or not isinstance(value.get("event"), str):
        raise ValueError("Native engine returned an invalid event")
    return value


def run_engine(arguments: list[str], session: Session, *, json_output: bool) -> int:
    binary = find_engine()
    token = os.environ.get("PYNGROK_TOKEN", "")
    if not 16 <= len(token.encode()) <= 1024:
        raise ValueError("Set PYNGROK_TOKEN to a shared secret of 16 to 1024 bytes")
    console = Console()
    interactive = console.is_terminal and not json_output
    # Inherit stderr so it cannot fill an unread pipe; tokens never enter argv.
    process = subprocess.Popen(
        [str(binary), *arguments], stdout=subprocess.PIPE, text=True, encoding="utf-8"
    )
    try:
        if process.stdout is None:
            raise RuntimeError("Failed to open engine event stream")
        with (
            Live(dashboard(session), console=console, auto_refresh=False)
            if interactive
            else _NullLive() as live
        ):
            while line := process.stdout.readline(MAX_EVENT_BYTES + 1):
                event = parse_event(line)
                session.update(event)
                if json_output:
                    sys.stdout.write(json.dumps(event, ensure_ascii=False) + "\n")
                    sys.stdout.flush()
                elif interactive:
                    live.update(dashboard(session), refresh=True)
                else:
                    console.print(line.rstrip(), markup=False, highlight=False)
        return process.wait()
    except KeyboardInterrupt:
        return 130
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        if process.stdout is not None:
            process.stdout.close()


class _NullLive:
    def __enter__(self) -> _NullLive:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def update(self, _renderable: object, *, refresh: bool) -> None:
        pass
