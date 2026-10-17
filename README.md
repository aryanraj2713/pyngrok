# ◈ pyngrok

A typed Python CLI with a Rust / Tokio reverse-tunnel engine and a neofetch-inspired terminal dashboard.

**Development status:** Python checks run locally. The Rust engine has not been compiled or exercised in this environment because a Rust toolchain is absent and shell network access is unavailable. This is an initial implementation, not a verified production tunnel or a complete reconstruction of ngrok. See [the investigation](docs/research/ngrok.md).

## Build and run

Homebrew development packaging is included in [Formula/pyngrok.rb](Formula/pyngrok.rb).
See the [Homebrew guide](packaging/homebrew/README.md) for the tap/install commands
and the pending publication/build checks. It installs the Python CLI and Rust
engine together; the public tap is not available yet.

Requires Python 3.11+, uv, and a stable Rust toolchain. From this checkout:

```sh
uv sync
cargo build --release --manifest-path crates/pyngrok-core/Cargo.toml
uv run pyngrok preview
uv run pyngrok doctor
```

Open three terminals with the **same** `PYNGROK_TOKEN` on relay and agent. Generate one with `uv run pyngrok keygen`, then export its output on each machine. Avoid putting secrets in command arguments or shell history.

```sh
# Terminal 1: relay, loopback-only by default
uv run pyngrok relay

# Terminal 2: your local application
python3 -m http.server 8000 --bind 127.0.0.1

# Terminal 3: expose the application through the relay
uv run pyngrok http 8000
# Also: uv run pyngrok tcp 22
```

Visit `http://<public_address>` from the `tunnel_ready` event/dashboard. Local defaults demonstrate forwarding on your own machine. To reach the internet, run the relay on a reachable server and configure its public host, interfaces, firewall, and TLS:

```sh
# Relay server; certificate must match relay.example.com
uv run pyngrok relay --bind 0.0.0.0:7443 \
  --public-bind 0.0.0.0 --public-host relay.example.com \
  --tls-cert server.pem --tls-key server-key.pem

# Developer machine, behind NAT
uv run pyngrok http 8000 --relay relay.example.com:7443 \
  --tls-server-name relay.example.com --public-port 18080
```

`--ca-cert` supports a private CA on the agent. TLS here protects **agent-to-relay traffic**. The dedicated public listener is raw TCP; the `http` command does not create an HTTPS URL or manage certificates. Serve TLS in the upstream application if required. Public ports expose your upstream service to callers; the shared token authenticates agents, not public visitors.

## Interface

- `http PORT` and `tcp HOST:PORT`: transparent byte forwarding, including WebSocket traffic.
- `relay`: run your relay with bounded connections and session-scoped tunnel listeners.
- `preview`: show labeled demo data without opening a tunnel.
- `keygen`, `doctor`, `version`: setup helpers.
- `--json`: newline JSON for scripts. Redirected output also avoids terminal animations.
- Ctrl+C: terminate the supervised engine and close the tunnel.

Use `--help` on any command. Tokens come from `PYNGROK_TOKEN`; `PYNGROK_CORE` overrides the native binary path. Installed Python packages discover the engine on PATH; source checkouts also find local Cargo builds. No Python forwarding fallback silently replaces Rust.

The requested command/import is `pyngrok`. The distribution is provisionally named `pyngrok-cli` because an unrelated [pyngrok package already exists](https://pypi.org/project/pyngrok/); do not install both into one environment. Distribution-name availability has not been checked for publication. This project does not use ngrok accounts or connect to ngrok infrastructure.

## Architecture and limitations

Python validates input, supervises the Rust process, and renders events. Rust owns listeners, TLS, authentication, tickets, connection tasks, backpressure, and bidirectional copying. Each public connection uses its own data channel, avoiding a Python copy loop and shared-stream head-of-line blocking. This incurs a data-connection/TLS handshake per client; throughput and latency need measurement before performance claims.

Read the [wire protocol](docs/protocol.md) for authentication and lifecycle details. There is no managed edge network, wildcard-domain HTTP routing, request inspector/replay, OAuth gateway, account system, automatic reconnect, or ngrok wire compatibility. A dropped session must be restarted. One agent process creates one endpoint.

## Checks

```sh
uv run ruff check .
uv run ruff format --check .
uv run ty check src
uv run pytest
cargo fmt --manifest-path crates/pyngrok-core/Cargo.toml --check
cargo clippy --manifest-path crates/pyngrok-core/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path crates/pyngrok-core/Cargo.toml
```

The integration test is skipped with an explicit reason when the native binary is absent. Python subprocess tests only establish CLI supervision; they do not establish Rust forwarding correctness. CI contains the Rust checks, but has not been run here.
