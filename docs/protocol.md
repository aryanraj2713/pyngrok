# pyngrok tunnel protocol v1

This independent implementation forwards raw TCP. HTTP, WebSocket and other TCP
protocols pass through unchanged. It does not connect to the hosted ngrok service
or implement ngrok's proprietary protocol, routing features or identity model.

The relay accepts TCP connections (TLS when configured). The first message is a
UTF-8 JSON object terminated by one newline, limited to 4096 bytes and ten seconds.
Every message has `version: 1`. The `type` field selects the message:

* `register`: `token`, `public_port` (0 requests an ephemeral port).
* `data`: `token`, `ticket` (random 256-bit hexadecimal capability).
* `ready`: relay response with `session_id` and `public_address`.
* `incoming`: relay control event containing a one-use `ticket`.
* `data_ready`: relay response on an accepted data socket. Bytes after this
  newline are raw TCP traffic, with no framing or interpretation.
* `ping` / `pong`: agent sends ping every ten seconds; idle control sockets expire
  after thirty seconds. Handshakes and control writes have bounded deadlines;
  raw application traffic can remain idle for the lifetime of its control session.
* `error`: `message` gives a non-secret failure reason.

For each public connection the relay creates a ticket, queues an incoming event,
and waits at most fifteen seconds for the agent's matching data connection.
Tickets belong to the control session, are consumed at most once, and are removed
on timeout or session teardown. Active forwarded sockets stop on session teardown.
The agent authenticates each data connection before the relay consumes its ticket.
The data socket receives `data_ready` before forwarding begins, preventing JSON
control frames from reaching the upstream application.

Authentication uses the `PYNGROK_TOKEN` environment variable exclusively, requires
at least sixteen bytes, and compares SHA-256 digests in constant time. Do not put
tokens in CLI arguments. The same configured token authorizes relay users;
multi-user isolation, token rotation and persistent identity are outside v1.
Neither peer logs the token. Ticket values must be treated as transient secrets.

Relay session count, connection tasks, pending public connections, and incoming
control queues are bounded. Excess sessions/connections are closed. Public and
upstream connection lifetimes are otherwise unlimited while the session lives.
The maximum frame size prevents unbounded JSON allocation; framing reads exactly
one byte at a time to preserve any application bytes after `data_ready`.

TLS uses rustls, server certificate verification and system-independent Web PKI
roots (or `--ca-cert`). There is no insecure certificate verification mode.
Plain relay transport is restricted to loopback unless `--allow-insecure` is
explicitly set. Public listener traffic itself is raw TCP, so applications must
provide their own HTTPS/TLS if public end-to-end encryption is required.

The `pyngrok-core` process emits newline-delimited JSON status events on stdout
and diagnostics on stderr. `relay_ready` supplies `bind`, `public_bind`, `tls`;
`tunnel_ready` supplies `public_address`, `upstream`, `session_id`;
`connection_open` supplies `connection_id`; `connection_close` additionally
supplies `bytes_up`, `bytes_down`; on a copy failure those counters are zero and
`counters_complete: false` marks unavailable partial counters. `connection_error`
supplies `message` for connection failures; `error` supplies `message` for fatal
failures; `stopped` marks graceful termination. Core reconnect is deliberately
left to the CLI/user.
