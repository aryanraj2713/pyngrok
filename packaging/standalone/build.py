"""Build a self-contained macOS archive; all compilers stay on the build machine."""

from __future__ import annotations

import hashlib
import json
import platform
import shutil
import subprocess
import sys
import tarfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run(*command: str) -> None:
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> None:
    if platform.system() != "Darwin":
        raise SystemExit("Standalone releases currently support macOS only")
    architectures = {"arm64": "arm64", "x86_64": "x86_64"}
    architecture = architectures[platform.machine()]
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    manifest = "crates/pyngrok-core/Cargo.toml"
    run("cargo", "build", "--release", "--locked", "--manifest-path", manifest)
    run(
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--name",
        "pyngrok",
        "--paths",
        "src",
        "--collect-submodules",
        "typer",
        "--collect-submodules",
        "rich",
        "--copy-metadata",
        "typer",
        "--copy-metadata",
        "rich",
        "--exclude-module",
        "tkinter",
        "--exclude-module",
        "pytest",
        "--distpath",
        "dist/standalone",
        "--workpath",
        "build/pyinstaller",
        "--specpath",
        "build",
        "src/pyngrok/__main__.py",
    )
    bundle = ROOT / "dist/standalone/pyngrok"
    shutil.copy2(ROOT / "crates/pyngrok-core/target/release/pyngrok-core", bundle)
    shutil.copy2(ROOT / "LICENSE", bundle)
    run("codesign", "--force", "--sign", "-", str(bundle / "pyngrok-core"))
    for command in ("version", "doctor", "preview"):
        run(str(bundle / "pyngrok"), command)
    archive = ROOT / f"dist/pyngrok-{version}-macos-{architecture}.tar.gz"
    with tarfile.open(archive, "w:gz") as output:
        output.add(bundle, arcname="pyngrok")
    with archive.open("rb") as archive_file:
        checksum = hashlib.file_digest(archive_file, "sha256").hexdigest()
    metadata = {
        "version": version,
        "architecture": architecture,
        "filename": archive.name,
        "sha256": checksum,
        "archive_bytes": archive.stat().st_size,
        "installed_bytes": sum(p.stat().st_size for p in bundle.rglob("*") if p.is_file()),
    }
    archive.with_suffix(".json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
