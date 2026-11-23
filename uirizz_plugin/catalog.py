"""Official Basic Catalog identity, allowlist, and admission caps."""

from __future__ import annotations

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

LIMITS = {
    "max_payload_bytes": 256 * 1024,
    "max_components": 100,
    "protocol": "1.0",
}
