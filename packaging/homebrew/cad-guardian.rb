class CadGuardian < Formula
  include Language::Python::Virtualenv

  desc "Policy-controlled AI CLI agent for power users"
  homepage "https://github.com/your-org/cad-guardian"
  url "https://github.com/your-org/cad-guardian/archive/refs/tags/v0.1.0.tar.gz"
  sha256 "REPLACE_WITH_RELEASE_TARBALL_SHA256"
  license "Proprietary"

  depends_on "python@3.12"

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "CAD Guardian CLI", shell_output("#{bin}/cg --help")
  end
end
