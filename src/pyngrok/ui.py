"""Neofetch-inspired terminal dashboard with a plain output fallback."""

from __future__ import annotations

import platform

from rich import box
from rich.columns import Columns
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from pyngrok import __version__
from pyngrok.models import Session

LOGO = r"""      ╭────────────╮
   ╭──┤  ▄▄▄  ▄▄▄  ├──╮
   │  │  █▄█  █▄█  │  │
   │  ╰────┬──┬────╯  │
   ╰───────┤  ├───────╯
       ▄▄▄▄█  █▄▄▄▄
       ▀▀▀▀▀  ▀▀▀▀▀"""


def dashboard(session: Session) -> Panel:
    info = Table.grid(padding=(0, 2))
    info.add_column(style="bold cyan")
    info.add_column()
    rows = [
        ("pyngrok", f"v{__version__} / {session.mode}"),
        ("system", f"{platform.system()} · {platform.machine()}"),
        ("engine", "Rust / Tokio"),
        ("status", session.status),
        ("forward", session.public_address),
        ("upstream", session.upstream),
        ("relay", session.relay),
        ("connections", f"{session.active} active · {session.total} total"),
        ("completed I/O", f"↑ {session.bytes_up:,} B   ↓ {session.bytes_down:,} B"),
    ]
    if session.last_error != "—":
        rows.append(("last error", session.last_error))
    for label, value in rows:
        info.add_row(Text(label), Text(value))
    return Panel(
        Group(
            Columns([Text(LOGO, style="bold cyan"), info], padding=(0, 3)),
            Text("\n  LOCAL IDEAS. GLOBAL CONNECTIONS.     ctrl+c to disconnect", style="dim"),
        ),
        title="[bold cyan]◈ pyngrok[/]  [dim]the tunnel is yours[/]",
        border_style="cyan",
        box=box.ROUNDED,
        padding=(1, 2),
    )
