class Pyngrok < Formula
  desc "Python command center for Rust-powered reverse tunnels"
  homepage "https://github.com/aryanraj2713/pyngrok"
  version "0.1.0-preview.1"
  license "MIT"
  depends_on macos: :sonoma

  on_macos do
    on_arm do
      url "https://github.com/aryanraj2713/pyngrok/releases/download/v0.1.0-preview.1/pyngrok-0.1.0-macos-arm64.tar.gz"
      sha256 "94e0535af49647b9c5eef84da3be101976e31250fc13546d70b76e6a649f28ea"
    end
    on_intel do
      url "https://github.com/aryanraj2713/pyngrok/releases/download/v0.1.0-preview.1/pyngrok-0.1.0-macos-x86_64.tar.gz"
      sha256 "2b4177fb444cb1acabf28144c9d1bda6b6443a06e74917194ec5a9baae753701"
    end
  end

  def install
    libexec.install Dir["*"]
    bin.install_symlink libexec/"pyngrok", libexec/"pyngrok-core"
  end

  test do
    native_version = shell_output("#{bin}/pyngrok-core --version").split.last
    assert_equal "pyngrok #{native_version}", shell_output("#{bin}/pyngrok version").strip
    assert_match "pyngrok-core", shell_output("#{bin}/pyngrok doctor")
    assert_match "no tunnel running", shell_output("#{bin}/pyngrok preview")
  end
end
