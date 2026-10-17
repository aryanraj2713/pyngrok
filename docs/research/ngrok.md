# ngrok investigation ledger

Date: 2026-10-18. Scope: agent lifecycle, transport, CLI, public routing, security, observability, and a Python/Rust reconstruction.

## Evidence boundary

REA MCP 6.5.0 is connected. `binary_session {}` reports no open target, Ghidra unconfigured, and Hopper missing. A compact session record is in [rea-session.json](rea-session.json). No ngrok binary was installed in the searched locations. Downloading the official Darwin arm64 archive failed with `curl: (6) Could not resolve host: bin.equinox.io`. Consequently **no ngrok artifact was analyzed**, and no REA artifact Evidence IDs, recovered functions, observed wire messages, or binary-derived conclusions are available. This report is documentation research plus our own implementation design. It does not establish complete understanding of ngrok.

## Findings and coverage

| Question | Evidence and conclusion | Status |
| --- | --- | --- |
| How does NAT traversal work? | Official agent documentation describes a long-lived outbound TLS session on port 443; traffic returns over agent connectivity without opening an inbound local port. | Answered from documentation; not observed at runtime |
| What owns endpoints? | Agent endpoints belong to a session and disappear when that session stops. An agent may create several endpoints. | Answered from documentation |
| How are disconnects handled? | Documentation describes heartbeats and automatic reconnection. Exact timing, backoff, and wire encoding are unobserved. | Partial |
| What does the CLI expose? | Official reference lists http/tcp/tls, config, start, diagnose, service, completion, API commands, and version/update operations. | Partial; no binary command inventory |
| Where do routing and access policies run? | Documentation places Traffic Policy in ngrok's network, ahead of forwarding to the agent. | Answered at conceptual level |
| What is the exact protocol? | Multiplexing details, authentication exchanges, frame layouts, resumption semantics, and client implementation are unknown. | Unresolved; requires artifact and controlled runtime captures |
| What happens inside the cloud? | Edge routing, scheduling, regional failover, storage, billing and identity implementations are not established by a client artifact. | Unresolved; server evidence required |
| How fast is it? | No target or implementation benchmark was run. | Unresolved |
| Can pyngrok connect to ngrok? | No compatibility protocol was recovered or implemented. pyngrok uses its own self-hosted protocol. | Explicit design boundary |

## Independent implementation choices

Typer supplies typed commands; Rich renders the terminal. Rust/Tokio owns all traffic forwarding. The reverse tunnel uses bounded JSON control messages and one authenticated data socket per public connection. It is a deliberately independent protocol, not a recovered ngrok protocol. Dedicated public ports allow HTTP and arbitrary TCP with the same transport. A future domain gateway would need HTTP routing, TLS termination, hostname allocation and certificate management.

## Next evidence needed

1. Obtain an official ngrok binary locally and record version, SHA-256, download source, and signature.
2. Run REA `inspect_go_binary` on that exact artifact for compiler/module metadata; presence of a module does not prove runtime use.
3. Configure an existing supported disassembler, open the artifact, and trace command registration, connection setup, authentication, heartbeat, reconnect, framing and forwarding with function-level Evidence IDs.
4. Run declared local CLI probes and controlled tunnel traffic using an authorized ngrok account. Keep secrets out of retained captures. Correlate behavior with static evidence.
5. Benchmark our compiled release build with concurrent HTTP/TCP traffic, large payloads, half-close, cancellation, upstream failure, and TLS. Record hardware, versions, payloads, p50/p95/p99, throughput, memory and CPU. Rust alone does not establish superior performance.

## Primary sources

- [How ngrok Agents Work](https://ngrok.com/docs/gateway/agent/how-it-works): session, endpoint lifecycle, heartbeats/reconnect, policy placement.
- [Agent CLI reference](https://ngrok.com/docs/gateway/agent/cli): documented commands and options.
- [Agent configuration v3](https://ngrok.com/docs/gateway/agent/config/v3): configuration surface.
- [Typer](https://github.com/fastapi/typer): typed CLI implementation library.
