import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "index.html").read_text(encoding="utf-8")
LAYOUT = (ROOT / "css" / "layout.css").read_text(encoding="utf-8")
COMPONENTS = (ROOT / "css" / "components.css").read_text(encoding="utf-8")
VARIABLES = (ROOT / "css" / "variables.css").read_text(encoding="utf-8")
CORE = (ROOT / "js" / "core.js").read_text(encoding="utf-8")

PRESERVED_IDS = {
    "chart-empty",
    "close-modal",
    "last-update",
    "main-index",
    "map-overlay-stats",
    "map-svg",
    "methodology-link",
    "methodology-modal",
    "next-update",
    "regional-summary",
    "signal-text",
    "status-pill",
    "status-text",
    "stream-feed",
    "trend-text",
    "trendChart",
    "utc-clock",
    "weights-table",
}


def test_runtime_selectors_and_script_order_remain_available():
    ids = set(re.findall(r'\bid=["\']([^"\']+)', HTML))
    assert PRESERVED_IDS <= ids
    scripts = re.findall(r'<script[^>]+src=["\']([^"\']+)', HTML)
    assert scripts[-5:] == [
        "bnti_data.js",
        "js/core.js",
        "js/map.js",
        "js/charts.js",
        "js/stream.js",
    ]
    assert "BNTI.init();" in HTML


def test_editorial_hierarchy_logo_endorsement_and_landmarks_are_visible():
    assert 'class="skip-link"' in HTML
    assert '<main id="main-content"' in HTML
    assert re.search(r"<h1[^>]*>\s*Border Neighbor Threat Index\s*</h1>", HTML)
    assert re.search(r'<img[^>]+class="brand-logo"[^>]+alt="[^"]*(?:BNTI|Border Neighbor)', HTML)
    assert "Part of Monarch Castle Technologies" in HTML
    assert "SDCofA" in HTML
    assert 'aria-label="Current index status and data freshness"' in HTML


def test_approved_wti_mena_token_roles_and_mobile_overflow_contract():
    for token in (
        "--bg: #15130f",
        "--bg-panel: #191711",
        "--text-primary: #ece6d8",
        "--text-secondary: #9a9284",
        "--accent: #c9a24b",
        '--serif: "Spectral"',
        '--sans: "IBM Plex Sans"',
        '--mono: "IBM Plex Mono"',
    ):
        assert token in VARIABLES
    combined = LAYOUT + COMPONENTS
    assert "overflow-x: clip" in combined
    assert re.search(r"@media\s*\(max-width:\s*720px\)", combined)
    assert re.search(r"\.content-shell\s*\{[^}]*width:\s*100%", combined, re.S)
    assert "minmax(0, 1fr)" in combined


def test_modal_and_map_are_keyboard_operable():
    assert 'role="dialog"' in HTML
    assert 'aria-modal="true"' in HTML
    assert 'aria-labelledby="methodology-title"' in HTML
    assert 'aria-expanded="false"' in HTML
    assert 'tabindex="0"' in HTML
    assert 'role="button"' in HTML
    assert "Escape" in CORE
    assert "focus()" in CORE

