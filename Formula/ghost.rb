class Ghost < Formula
  desc "Local security reviews with evidence-gated repairs"
  homepage "https://github.com/Devesh36/ghost"
  license "MIT"
  head "https://github.com/Devesh36/ghost.git", branch: "main"

  depends_on "git"
  depends_on "python@3.12"
  depends_on "uv"
  on_linux do
    depends_on "bubblewrap"
  end

  def install
    # Install the locked dependencies and Ghost into a dedicated environment.
    with_env UV_PROJECT_ENVIRONMENT: libexec.to_s, UV_PYTHON_DOWNLOADS: "never", UV_NO_CACHE: "1" do
      system Formula["uv"].opt_bin/"uv", "sync", "--frozen", "--no-dev", "--no-editable",
             "--python", Formula["python@3.12"].opt_bin/"python3.12"
    end
    bin.install_symlink libexec/"bin/ghost"
  end

  def caveats
    <<~EOS
      Run ghost doctor, then ghost find inside your Git project.
      This installs the development version from main.
      Python repairs run with #{libexec}/bin/python; project test dependencies
      must be installed in that environment. See docs/getting-started.md.
    EOS
  end

  test do
    assert_match "find security risks", shell_output("#{bin}/ghost --help")
    system bin/"ghost", "demo", "--security"
  end
end
