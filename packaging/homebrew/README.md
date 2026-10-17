# Homebrew distribution

`Formula/pyngrok.rb` installs both commands: `pyngrok` (an isolated Python CLI)
and `pyngrok-core` (a release-mode Rust binary). The launcher selects its bundled
engine explicitly, so another installation on PATH cannot silently replace it.
Rust and uv are build-only dependencies; Homebrew supplies the Python runtime.

## Development installation

These commands become usable **after** the public repository exists and contains
this code. It has not been published or installed through Homebrew yet:

```sh
brew tap aryanraj2713/pyngrok https://github.com/aryanraj2713/pyngrok.git
brew install --HEAD aryanraj2713/pyngrok/pyngrok
brew test aryanraj2713/pyngrok/pyngrok
pyngrok preview
```

An explicit tap URL allows the source repository to double as a tap without a
separate `homebrew-pyngrok` repository. This is a development HEAD formula, not a
Homebrew/core submission or a stable release.

Homebrew's network-enabled `fetch` phase resolves the Python requirements into a
hash-checked requirements file and downloads their wheels. Cargo resolves a
lockfile when the source does not contain one, then fetches locked dependencies.
The subsequent installation builds Rust offline, installs the Python CLI into a
private virtual environment offline, and installs a launcher with the engine path.
Resolution is reproducible within that installation; until release lockfiles are
committed, separate HEAD builds can resolve different dependency versions.

## Validation and stable release

Local validation covers Ruby syntax. Homebrew refused to load a standalone formula
outside a tap, and tap initialization is blocked by this session's filesystem permissions.
A full `brew install`, native build, `brew test`, and audit still need to run on a
network-enabled machine with write access to Homebrew directories. Normal
Homebrew installation will install its missing Rust build dependency.

Before a stable release:

1. Compile and test the native engine and run `cargo fmt`/Clippy.
2. Commit Cargo and Python dependency locks and pin Python formula resources.
3. Tag a tested release; replace HEAD-only distribution with its source archive
   URL and actual SHA-256. Retain the HEAD stanza for development if desired.
4. Install/test the formula on macOS arm64 and x86_64, then build bottles to avoid
   compiling Rust on each user's computer.

Reference: [Homebrew Formula Cookbook](https://docs.brew.sh/Formula-Cookbook),
including its `fetch` phase and offline installation contract.
