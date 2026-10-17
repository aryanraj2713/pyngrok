class Pyngrok < Formula
  desc "Python command center for Rust-powered reverse tunnels"
  homepage "https://github.com/aryanraj2713/pyngrok"
  license "MIT"
  head "https://github.com/aryanraj2713/pyngrok.git", branch: "main"

  depends_on "rust" => :build
  depends_on "uv" => :build
  depends_on "python@3.13"

  # Development-only HEAD formula. Resolve dependencies during Homebrew's
  # network-enabled fetch phase; install runs entirely offline.
  def fetch
    cd "crates/pyngrok-core" do
      system "cargo", "generate-lockfile" unless File.exist?("Cargo.lock")
      system "cargo", "fetch", *std_cargo_fetch_args
    end

    ENV["UV_CACHE_DIR"] = buildpath/"uv-cache"
    python = Formula["python@3.13"].opt_bin/"python3.13"
    system "uv", "pip", "compile", "pyproject.toml", "packaging/homebrew/build.in",
           "--python", python, "--generate-hashes", "--output-file", buildpath/"requirements.txt"
    system python, "-m", "pip", "download", "--disable-pip-version-check", "--no-cache-dir",
           "--require-hashes", "--only-binary=:all:", "--dest", buildpath/"wheelhouse",
           "--requirement", buildpath/"requirements.txt"
  end

  def install
    system "cargo", "install", *std_cargo_args(path: "crates/pyngrok-core")

    python = Formula["python@3.13"].opt_bin/"python3.13"
    system python, "-m", "venv", libexec
    venv_python = libexec/"bin/python"
    system venv_python, "-m", "pip", "install", "--disable-pip-version-check",
           "--no-index", "--find-links=#{buildpath}/wheelhouse", "--require-hashes",
           "--requirement", buildpath/"requirements.txt"
    system venv_python, "-m", "pip", "install", "--disable-pip-version-check",
           "--no-index", "--no-deps", "--no-build-isolation", "."
    (bin/"pyngrok").write_env_script libexec/"bin/pyngrok",
                                   PYNGROK_CORE: bin/"pyngrok-core"
  end

  def caveats
    <<~EOS
      This is an experimental HEAD build. Native transport verification is pending.
      Generate a shared secret with `pyngrok keygen` and set PYNGROK_TOKEN on both peers.
      Run `pyngrok relay` on your server and `pyngrok http 8000` on your workstation.
      Run `pyngrok preview` to see the dashboard without opening a tunnel.
    EOS
  end

  test do
    native_version = shell_output("#{bin}/pyngrok-core --version").split.last
    assert_equal "pyngrok #{native_version}", shell_output("#{bin}/pyngrok version").strip
    assert_match "pyngrok-core", shell_output("#{bin}/pyngrok doctor")
    assert_match "no tunnel running", shell_output("#{bin}/pyngrok preview")
    assert_operator shell_output("#{bin}/pyngrok keygen").strip.length, :>=, 32
    assert_match "pyngrok-core", shell_output("#{bin}/pyngrok-core --version")
  end
end
