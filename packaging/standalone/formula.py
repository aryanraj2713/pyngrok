"""Generate a dependency-free Homebrew formula from measured release assets."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def generate(assets: Path, tag: str) -> str:
    if not re.fullmatch(r"v\d+\.\d+\.\d+(?:-preview\.\d+)?", tag):
        raise ValueError("Expected a version tag such as v0.1.0-preview.1")
    metadata: dict[str, dict[str, str]] = {}
    for path in assets.glob("*.tar.json"):
        value = json.loads(path.read_text())
        architecture = value["architecture"]
        if architecture not in {"arm64", "x86_64"} or architecture in metadata:
            raise ValueError("Unexpected or duplicate release architecture")
        expected = f"pyngrok-{value['version']}-macos-{architecture}.tar.gz"
        if value["filename"] != expected or not re.fullmatch(r"[a-f0-9]{64}", value["sha256"]):
            raise ValueError("Invalid release asset metadata")
        metadata[architecture] = value
    if set(metadata) != {"arm64", "x86_64"}:
        raise ValueError("Both macOS architectures are required")
    if {m["version"] for m in metadata.values()} != {tag[1:].split("-preview.")[0]}:
        raise ValueError("Release tag and payload versions do not match")
    blocks = []
    for architecture, stanza in (("arm64", "on_arm"), ("x86_64", "on_intel")):
        value = metadata[architecture]
        blocks.append(f'''    {stanza} do
      url "https://github.com/aryanraj2713/pyngrok/releases/download/{tag}/{value["filename"]}"
      sha256 "{value["sha256"]}"
    end''')
    platforms = "\n".join(blocks)
    return f'''class Pyngrok < Formula
  desc "Python command center for Rust-powered reverse tunnels"
  homepage "https://github.com/aryanraj2713/pyngrok"
  version "{tag[1:]}"
  license "MIT"
  depends_on macos: :sonoma

  on_macos do
{platforms}
  end

  def install
    libexec.install Dir["*"]
    bin.install_symlink libexec/"pyngrok", libexec/"pyngrok-core"
  end

  test do
    native_version = shell_output("#{{bin}}/pyngrok-core --version").split.last
    assert_equal "pyngrok #{{native_version}}", shell_output("#{{bin}}/pyngrok version").strip
    assert_match "pyngrok-core", shell_output("#{{bin}}/pyngrok doctor")
    assert_match "no tunnel running", shell_output("#{{bin}}/pyngrok preview")
  end
end
'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(generate(args.assets, args.tag))


if __name__ == "__main__":
    main()
