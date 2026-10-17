# Lightweight Homebrew distribution

The source-only `--HEAD` installation builds Rust on each user's Mac. Homebrew
then installs Rust, LLVM, uv, Python and their dependencies. Those are build tools
and interpreter dependencies, not the size of the tunnel engine. The optimized
Rust binary measured about 4 MiB on macOS arm64; the complete standalone package
includes the Python interpreter and CLI libraries and is larger.

## Prebuilt distribution

`.github/workflows/release.yml` builds standalone packages on macOS arm64 and
Intel runners. PyInstaller bundles Python and the CLI as an ordinary directory;
the compiled Rust engine sits beside the launcher. There is no per-command
self-extraction. End users do not need Rust, LLVM, uv or Homebrew Python.

After tests on both architectures pass, the workflow publishes a prerelease,
records each archive's SHA-256 and actual compressed/installed size, and commits
the generated binary formula to `Formula/pyngrok.rb`. Until that first release
succeeds, the existing default formula is still the source-build version.

**Use these commands only after the standalone release/formula update succeeds:**

```sh
brew tap aryanraj2713/pyngrok https://github.com/aryanraj2713/pyngrok.git
brew update
brew install aryanraj2713/pyngrok/pyngrok
pyngrok preview
```

The prebuilt formula supports macOS 14+ and has no Homebrew package dependencies.
It copies a complete runtime and symlinks the two commands. The release archive
and formula checksums come from the same tested build; no placeholder URLs or
checksums are committed. The packages are ad-hoc signed, not Developer ID signed
or notarized. Their full download size and cold startup time remain unmeasured
until the first standalone build completes.

## Source builds for developers

`Formula/pyngrok-source.rb` retains the original build process:

```sh
brew install --HEAD aryanraj2713/pyngrok/pyngrok-source
```

Both formulae export the same command names; use one installation at a time.
The source formula resolves/fetches dependencies during Homebrew's network-enabled
`fetch` phase and installs offline. The Rust lockfile is now committed.

## Release and verification

Packaging changes pushed to main trigger the standalone workflow; it can also be
started with `gh workflow run release.yml --repo aryanraj2713/pyngrok`. It checks
Python and Rust, tests real native TCP/TLS forwarding, and smoke-tests the frozen
launcher with no Python or Rust on PATH. Release publication requires both matrix
builds; failed checks leave the current Homebrew formula unchanged.

The final workflow step pushes the formula update without force; a concurrent
main update may require rerunning the release. Existing prerelease assets are
never overwritten. Source builds are for development; ordinary users should use
the default prebuilt formula without `--HEAD` once available.

References: [Homebrew binary packages](https://docs.brew.sh/Bottles),
[PyInstaller bundles](https://pyinstaller.org/en/stable/operating-mode.html).
