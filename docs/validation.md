# Validation record

Local environment: macOS arm64, Python 3.12.11, 2026-10-18.

- Python tests: 25 passed; 3 native integration tests skipped because no engine binary exists.
- Ruff lint and formatting checks: passed.
- ty static checking of `src`: passed.
- Python wheel: built successfully with setuptools; includes console entrypoint and `py.typed`.
- CLI help and labeled dashboard preview: executed successfully.
- Native source: reviewed, eight unit tests written; compile, rustfmt, Clippy and native tests unexecuted.
- CI: configured for Python checks, Rust formatting/Clippy/unit tests, and real native integration tests; not run here.
- Throughput, latency, memory, load and public-server deployment: unmeasured/unverified.
- ngrok artifact analysis: blocked; no local target binary, download failed DNS resolution. Only REA session discovery and primary documentation research completed.

The local Python virtual environment uses available cached dependencies through a `.pth` file because uv's installer panicked in this sandbox's macOS system configuration API. Pytest plugin autoload was disabled to exclude unrelated cached package plugins. No system package installation or client configuration was changed. A fresh normal environment should use the README's `uv sync` command. Dependency lockfiles await network-enabled resolution.

The initial native implementation still requires a toolchain pass, including `cargo fmt`, compilation and full integration tests before being considered runnable. Passing Python checks does not establish native transport correctness or security. The Python wheel expects a separately built native binary; it does not bundle one.

Homebrew: development HEAD formula added. Ruby syntax passes; full Homebrew loading/install/test is blocked by tap/cache filesystem restrictions and network access. No stable release or public tap exists yet.

GitHub publication: the connected account is `aryanraj2713`. Creating public repository `aryanraj2713/pyngrok` through the installed `gh` CLI failed because it cannot connect to `api.github.com`. The GitHub connector has no repository-creation capability. The workspace's `.git` path is read-only, so the prepared commit uses a separate temporary Git directory and is exported as `dist/pyngrok.bundle`. `scripts/publish-github.sh` clones that bundle into a temporary checkout and creates/pushes the public repository when run with network access. The bundle excludes dependency caches, local environments, build outputs, and raw machine-local REA configuration.
