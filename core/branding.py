"""Shared branding assets used across every tool page.

The logo is loaded from assets/logo.png rather than embedded as base64 in
source. Drop your WRA logo PNG at that path (see assets/README.txt) and every
page will pick it up automatically.
"""

from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = APP_ROOT / "assets" / "logo.png"

BRAND_DARK = "#003B5C"


def logo_path_if_present():
    """Return the logo path if the file exists, else None."""
    return LOGO_PATH if LOGO_PATH.exists() else None
