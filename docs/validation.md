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

GitHub publication: the connected account is `aryanraj2713`. This session's installed `gh` cannot connect to `api.github.com`. The user ran the publish script in their terminal and created public repository `aryanraj2713/pyngrok`; GitHub rejected the initial push because their OAuth token lacks the `workflow` scope required to upload `.github/workflows/check.yml`. The updated script reuses the existing public repository and reports the required `gh auth refresh --hostname github.com --scopes workflow` command on that failure. It never force-pushes or silently changes repository visibility.

The workspace's `.git` path is read-only, so the prepared commit uses a separate temporary Git directory and is exported as `dist/pyngrok.bundle`. The publish script clones that bundle into a temporary checkout and creates or reuses the public repository. The bundle excludes dependency caches, local environments, build outputs, and raw machine-local REA configuration. Shell syntax and isolated checks for existing-repository retry and workflow-scope error handling pass; the successful GitHub push remains pending.
