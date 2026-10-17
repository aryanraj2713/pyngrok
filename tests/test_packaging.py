from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from pyngrok.engine import find_engine

FORMULA_SCRIPT = Path(__file__).resolve().parents[1] / "packaging/standalone/formula.py"
spec = importlib.util.spec_from_file_location("standalone_formula", FORMULA_SCRIPT)
assert spec is not None and spec.loader is not None
formula = importlib.util.module_from_spec(spec)
spec.loader.exec_module(formula)


def assets(directory: Path) -> None:
    for architecture in ("arm64", "x86_64"):
        (directory / f"{architecture}.tar.json").write_text(
            json.dumps(
                {
                    "version": "0.1.0",
                    "architecture": architecture,
                    "filename": f"pyngrok-0.1.0-macos-{architecture}.tar.gz",
                    "sha256": "a" * 64,
                }
            )
        )


def test_binary_formula_has_no_toolchain_or_python_dependency(tmp_path: Path) -> None:
    assets(tmp_path)
    result = formula.generate(tmp_path, "v0.1.0-preview.1")
    assert "depends_on macos: :sonoma" in result
    assert "releases/download/v0.1.0-preview.1/" in result
    for dependency in ('"rust"', '"uv"', '"python@3.13"'):
        assert dependency not in result
    assert 'sha256 "' + "a" * 64 + '"' in result


def test_formula_requires_both_platforms(tmp_path: Path) -> None:
    assets(tmp_path)
    (tmp_path / "arm64.tar.json").unlink()
    with pytest.raises(ValueError, match="Both macOS"):
        formula.generate(tmp_path, "v0.1.0")


@pytest.mark.parametrize("tag", ["v0.2.0", 'v0.1.0"; system("bad")', "latest"])
def test_formula_rejects_mismatched_or_unsafe_release_tag(tmp_path: Path, tag: str) -> None:
    assets(tmp_path)
    with pytest.raises(ValueError):
        formula.generate(tmp_path, tag)


def test_frozen_launcher_prefers_its_bundled_engine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "pyngrok").touch()
    binary = tmp_path / "pyngrok-core"
    binary.write_text("#!/bin/sh\nexit 0\n")
    binary.chmod(0o755)
    monkeypatch.delenv("PYNGROK_CORE", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "pyngrok"))
    assert find_engine() == binary
    binary.unlink()
    with pytest.raises(ValueError, match="Bundled Rust engine"):
        find_engine()
