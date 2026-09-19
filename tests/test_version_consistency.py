"""La version est ecrite a la main a deux endroits : ils doivent rester d'accord (branding.js et entete du README)."""
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent


def test_readme_header_version_matches_the_app_version():
    branding = (ROOT / "frontend" / "js" / "branding.js").read_text(encoding="utf-8")
    app_version = re.search(r'APP_BUILD_VERSION\s*=\s*"([^"]+)"', branding).group(1)
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    versions = set(re.findall(r"`(\d+\.\d+\.\d+(?:-[a-z]+)?)`", readme[:1500]))
    assert app_version in versions, f"README (entete) annonce {sorted(versions)}, l'application est en {app_version}"
