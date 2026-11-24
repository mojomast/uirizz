"""Official Basic Catalog identity, allowlist, and admission caps."""

from __future__ import annotations

from pathlib import Path

BASIC_CATALOG_ID = "https://a2ui.org/specification/v1_0/catalogs/basic/catalog.json"

BASIC_COMPONENTS = (
    "Text",
    "Image",
    "Icon",
    "Video",
    "AudioPlayer",
    "Row",
    "Column",
    "List",
    "Card",
    "Tabs",
    "Divider",
    "Modal",
    "Button",
    "TextField",
    "CheckBox",
    "ChoicePicker",
    "Slider",
    "DateTimeInput",
)

# Video and AudioPlayer stay listed for describe(), but admission rejects them
# until a later cut proves the same URL guard on media players.
MVP_COMPONENTS = tuple(
    name for name in BASIC_COMPONENTS if name not in {"Video", "AudioPlayer"}
)

UIRIZZ_CATALOG_ID = "https://github.com/mojomast/uirizz/catalogs/v1/catalog.json"
UIRIZZ_CATALOG_PATH = Path(__file__).resolve().parent / "catalogs" / "uirizz_v1.json"

# Data components added on top of the Basic Catalog; admitted only under UIRIZZ_CATALOG_ID.
UIRIZZ_COMPONENTS = (
    "Chart",
    "DataTable",
    "Metric",
    "Progress",
    "Badge",
    "Callout",
    "KeyValueList",
    "Timeline",
    "CodeBlock",
)

ADMITTED_COMPONENTS = MVP_COMPONENTS + UIRIZZ_COMPONENTS

LIMITS = {
    "max_payload_bytes": 256 * 1024,
    "max_components": 100,
    "max_literal_rows": 500,
    "max_array_items": 5000,
    "protocol": "1.0",
}
