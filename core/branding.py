"""Shared branding assets used across every tool page.

The logo is loaded from assets/logo.png rather than embedded as base64 in
source. Drop your WRA logo PNG at that path (see assets/README.txt) and every
page will pick it up automatically.

Color values below are copied directly from WRA_Brand_Guide_Revised_2026.pdf
(section 04, Colors) -- not invented placeholders. BRAND_DARK is sampled
straight from the logo wordmark ink, which matches TERRACOTA_SHADE exactly.
"""

from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
LOGO_PATH = APP_ROOT / "assets" / "logo.png"

# ── WRA brand palette (Brand Guide section 04) ────────────────────────────────
# Primary five
TERRACOTA      = "#C76E4F"
CALIFORNIA_SUNSET = "#D4822B"
MOSS_GREEN     = "#A19100"
FIELD_GREEN    = "#529E2E"
OCEAN_BLUE     = "#5CB5BD"

# Shades (darker variants)
TERRACOTA_SHADE      = "#7D3B2E"
CALIFORNIA_SUNSET_SHADE = "#944F15"
MOSS_GREEN_SHADE     = "#65590F"
FIELD_GREEN_SHADE    = "#175536"
OCEAN_BLUE_SHADE     = "#0A596A"

# Tints (lighter variants)
TERRACOTA_TINT      = "#FFD8B2"
CALIFORNIA_SUNSET_TINT = "#FFDF95"
MOSS_GREEN_TINT     = "#DFE78A"
FIELD_GREEN_TINT    = "#CCF3BA"
OCEAN_BLUE_TINT     = "#C4EEF2"

# Backgrounds / text ink
NEUTRAL_BACKGROUND = "#FEF9F0"
WARMER_CREAM       = "#FFEACE"
DARK_BROWN         = "#421B03"
BODY_COPY          = "#2D1603"

# Title/heading color used across every page -- sampled directly from the
# logo wordmark, which matches TERRACOTA_SHADE.
BRAND_DARK = TERRACOTA_SHADE

# Brand type hierarchy (Brand Guide section 05): Archia is primary, Tenorite
# is the Office-compatible fallback, Verdana is tertiary (email-only, but a
# safe last resort here since it ships with virtually every OS/browser).
BRAND_FONT_STACK = ["Archia", "Tenorite", "Verdana", "sans-serif"]


def logo_path_if_present():
    """Return the logo path if the file exists, else None."""
    return LOGO_PATH if LOGO_PATH.exists() else None
