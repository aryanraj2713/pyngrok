"""Validated boundaries between command input and the native engine."""

from __future__ import annotations

from dataclasses import dataclass
from ipaddress import ip_address


def endpoint(value: str, *, default_host: str | None = None) -> str:
    """Normalize a port or host:port, including bracketed IPv6 literals."""
    value = value.strip()
    if value.isdecimal() and default_host is not None:
        value = f"{default_host}:{value}"
    if value.startswith("["):
        host, separator, port = value[1:].partition("]:")
        if not separator:
            raise ValueError("IPv6 addresses must use [address]:port")
        address = ip_address(host)
        if address.version != 6:
            raise ValueError("Brackets require an IPv6 address")
        host = f"[{address}]"
    else:
        host, separator, port = value.rpartition(":")
        if not separator or ":" in host:
            raise ValueError("Use a port, host:port, or [IPv6]:port")
        if not host or any(c.isspace() or c in "/\\?#@[]" for c in host):
            raise ValueError("Host must be a hostname or IP address")
    if not port.isascii() or not port.isdecimal() or not 1 <= int(port) <= 65535:
        raise ValueError("Port must be between 1 and 65535")
    return f"{host}:{int(port)}"


@dataclass(slots=True)
class Session:
    """Display state; never carries transport buffers or credentials."""

    mode: str
    upstream: str = "—"
    relay: str = "—"
    status: str = "connecting"
    public_address: str = "waiting for relay"
    active: int = 0
    total: int = 0
    bytes_up: int = 0
    bytes_down: int = 0
    last_error: str = "—"

    def update(self, event: dict[str, object]) -> None:
        kind = event.get("event")
        if kind == "tunnel_ready":
            self.status = "online"
            self.public_address = str(event.get("public_address", "—"))
        elif kind == "relay_ready":
            self.status = "listening"
            self.public_address = str(event.get("bind", "—"))
        elif kind == "connection_open":
            self.active += 1
            self.total += 1
        elif kind == "connection_close":
            self.active = max(0, self.active - 1)
            self.bytes_up += nonnegative_int(event.get("bytes_up"))
            self.bytes_down += nonnegative_int(event.get("bytes_down"))
        elif kind == "error":
            self.last_error = str(event.get("message", "Unknown engine error"))
        elif kind == "connection_error":
            if isinstance(event.get("connection_id"), str):
                self.active = max(0, self.active - 1)
            self.last_error = str(event.get("message", "Connection failed"))
        elif kind == "stopped":
            self.status = "stopped"


def nonnegative_int(value: object) -> int:
    return max(0, value) if isinstance(value, int) and not isinstance(value, bool) else 0
