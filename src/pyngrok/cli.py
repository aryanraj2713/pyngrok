"""Typed command surface for pyngrok."""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from pyngrok import __version__
from pyngrok.engine import find_engine, run_engine
from pyngrok.models import Session, endpoint
from pyngrok.ui import dashboard

app = typer.Typer(no_args_is_help=True, help="◈ pyngrok · Python soul. Rust speed.")
Port = Annotated[int, typer.Option(min=0, max=65535, help="Relay-side port; 0 allocates one.")]
Relay = Annotated[str, typer.Option(help="Relay control address (host:port).")]
Json = Annotated[bool, typer.Option("--json", help="Emit newline JSON events without a dashboard.")]
Insecure = Annotated[bool, typer.Option(help="Explicitly allow unencrypted remote relay traffic.")]
Name = Annotated[
    str | None, typer.Option(help="Enable TLS and verify this relay certificate name.")
]
CA = Annotated[Path | None, typer.Option(exists=True, dir_okay=False, help="Custom CA PEM file.")]


def execute(arguments: list[str], session: Session, json_output: bool) -> None:
    try:
        code = run_engine(arguments, session, json_output=json_output)
    except (ValueError, OSError) as error:
        Console(stderr=True).print(f"Error: {error}", style="red", markup=False)
        raise typer.Exit(1) from error
    raise typer.Exit(code)


def connect(
    target: str,
    relay: str,
    public_port: int,
    json_output: bool,
    allow_insecure: bool,
    tls_server_name: str | None,
    ca_cert: Path | None,
    mode: str,
) -> None:
    try:
        upstream = endpoint(target, default_host="127.0.0.1")
        relay = endpoint(relay)
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error
    if ca_cert is not None and tls_server_name is None:
        raise typer.BadParameter("--ca-cert requires --tls-server-name")
    arguments = [
        "connect",
        "--upstream",
        upstream,
        "--relay",
        relay,
        "--public-port",
        str(public_port),
    ]
    if allow_insecure:
        arguments.append("--allow-insecure")
    if tls_server_name:
        arguments.extend(["--tls-server-name", tls_server_name])
    if ca_cert:
        arguments.extend(["--ca-cert", str(ca_cert)])
    execute(arguments, Session(mode=mode, upstream=upstream, relay=relay), json_output)


@app.command()
def tcp(
    target: Annotated[str, typer.Argument(help="Local port or host:port to expose.")],
    relay: Relay = "127.0.0.1:7443",
    public_port: Port = 0,
    json_output: Json = False,
    allow_insecure: Insecure = False,
    tls_server_name: Name = None,
    ca_cert: CA = None,
) -> None:
    """Expose a TCP service through your relay."""
    connect(
        target, relay, public_port, json_output, allow_insecure, tls_server_name, ca_cert, "tcp"
    )


@app.command()
def http(
    target: Annotated[str, typer.Argument(help="Local HTTP port or host:port to expose.")],
    relay: Relay = "127.0.0.1:7443",
    public_port: Port = 0,
    json_output: Json = False,
    allow_insecure: Insecure = False,
    tls_server_name: Name = None,
    ca_cert: CA = None,
) -> None:
    """Forward HTTP bytes transparently; the public endpoint uses a dedicated TCP port."""
    connect(
        target, relay, public_port, json_output, allow_insecure, tls_server_name, ca_cert, "http"
    )


@app.command()
def relay(
    bind: Annotated[str, typer.Option(help="Control listener host:port.")] = "127.0.0.1:7443",
    public_bind: Annotated[
        str, typer.Option(help="Interface for public tunnel listeners.")
    ] = "127.0.0.1",
    public_host: Annotated[str, typer.Option(help="Hostname advertised to agents.")] = "127.0.0.1",
    tls_cert: CA = None,
    tls_key: CA = None,
    allow_insecure: Insecure = False,
    json_output: Json = False,
    max_connections: Annotated[int, typer.Option(min=1, max=4096)] = 256,
) -> None:
    """Run the self-hosted relay on your server."""
    try:
        bind = endpoint(bind)
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error
    if (tls_cert is None) != (tls_key is None):
        raise typer.BadParameter("--tls-cert and --tls-key must be supplied together")
    arguments = [
        "relay",
        "--bind",
        bind,
        "--public-bind",
        public_bind,
        "--public-host",
        public_host,
        "--max-connections",
        str(max_connections),
    ]
    if tls_cert and tls_key:
        arguments.extend(["--tls-cert", str(tls_cert), "--tls-key", str(tls_key)])
    if allow_insecure:
        arguments.append("--allow-insecure")
    execute(arguments, Session(mode="relay", relay=bind), json_output)


@app.command()
def doctor() -> None:
    """Check whether the Rust engine is available."""
    try:
        binary = find_engine()
    except ValueError as error:
        Console(stderr=True).print(str(error), markup=False)
        raise typer.Exit(1) from error
    Console().print(f"Engine: {binary}", markup=False)


@app.command()
def keygen() -> None:
    """Generate a shared secret; export it as PYNGROK_TOKEN on relay and agent."""
    typer.echo(secrets.token_urlsafe(32))


@app.command()
def version() -> None:
    """Print the Python CLI version."""
    typer.echo(f"pyngrok {__version__}")


@app.command()
def preview() -> None:
    """Preview the terminal interface with explicitly labeled demo data."""
    Console().print(
        dashboard(
            Session(
                mode="demo / preview",
                upstream="127.0.0.1:8000",
                relay="relay.example:7443",
                status="demo · no tunnel running",
                public_address="relay.example:49152",
                active=3,
                total=42,
                bytes_up=12480,
                bytes_down=918240,
            )
        )
    )
