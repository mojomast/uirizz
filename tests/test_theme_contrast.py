"""Night Hive text colors meet WCAG 2.2 AA contrast (4.5:1) on dark surfaces."""

from __future__ import annotations

from uirizz_plugin.theme import NIGHT_HIVE


def _lin(channel: float) -> float:
    c = channel / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _lum(hex_color: str) -> float:
    value = hex_color.removeprefix("#")
    r = int(value[0:2], 16)
    g = int(value[2:4], 16)
    b = int(value[4:6], 16)
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contrast(fg: str, bg: str) -> float:
    light, dark = max(_lum(fg), _lum(bg)), min(_lum(fg), _lum(bg))
    return (light + 0.05) / (dark + 0.05)


def test_text_and_accent_contrast_aa():
    base = NIGHT_HIVE["base"]
    surface = NIGHT_HIVE["surface"]
    for name in ("text", "muted", "honey", "mint", "red"):
        for bg in (base, surface):
            ratio = contrast(NIGHT_HIVE[name], bg)
            assert ratio >= 4.5, f"{name} on {bg} is {ratio:.2f}:1"

    for accent in ("honey", "mint", "red"):
        ratio = contrast(NIGHT_HIVE["base"], NIGHT_HIVE[accent])
        assert ratio >= 4.5, f"base on {accent} is {ratio:.2f}:1"
