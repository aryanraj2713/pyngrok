# Validation record

Local environment: macOS arm64, Python 3.12.11, 2026-10-18.

- Python unit and packaging tests: 31 passed.
- Ruff lint/format and ty checking of `src`: passed.
- Rust: eight unit tests passed, rustfmt passed, Clippy passed with warnings denied.
- Rust release binary: compiled offline with the committed Cargo.lock; approximately 4 MiB before the additional thin-LTO release profile.
- Native TCP/TLS integration: three tests attempted and blocked by sandbox socket permissions (`Operation not permitted`); not counted as passed.
- Standalone packaging: build scripts, metadata validation, bundled-engine discovery and generated formula tested locally. PyInstaller is unavailable locally, so complete macOS packages await CI builds.
- Python wheel: built successfully with setuptools; includes console entrypoint and `py.typed`.
- Homebrew: source formula syntax passed, public tap/code now exist. Source installation pulled compiler dependencies and encountered Homebrew's OpenSSL sibling-lock bug. The standalone release workflow will replace the default formula only after both architecture builds/tests pass.
- Standalone compressed/installed size, startup latency, throughput and public-server deployment: unmeasured/unverified.
- ngrok artifact analysis: no local ngrok binary available; only REA session discovery and primary documentation research completed.

The initial local Python environment uses cached dependencies through a `.pth` file because uv's installer initially panicked in this sandbox. Pytest plugin autoload is disabled locally to exclude unrelated cached plugins. The user subsequently installed Homebrew's Rust toolchain; cached crates made offline native builds possible. No system packages were installed by the agent.

The workspace's `.git` is read-only. Local commits use a separate temporary Git directory and `dist/pyngrok.bundle`; public changes can also be pushed through the connected GitHub tools. Machine-local REA paths, caches, virtual environments and build outputs are excluded from public source.
