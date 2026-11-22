"""Loads theme.qss and exposes its colour variables to the Python code.

The stylesheet uses ``@name: value;`` variables (plain QSS has none). They're
substituted into the stylesheet, and also exposed here as constants so code
that paints by hand (covers, achievement rows, popups) uses the same colours.
"""
from __future__ import annotations

import re
from pathlib import Path

THEME_FILE = Path(__file__).with_name("theme.qss")
_VAR = re.compile(r"^\s*@([\w-]+)\s*:\s*([^;]+);", re.M)


def _load() -> tuple[dict[str, str], str]:
    text = THEME_FILE.read_text(encoding="utf-8")
    colors = {k: v.strip() for k, v in _VAR.findall(text)}
    body = _VAR.sub("", text)
    # longest names first so @panel-hover isn't replaced as @panel + "-hover"
    for name in sorted(colors, key=len, reverse=True):
        body = body.replace(f"@{name}", colors[name])
    return colors, body


COLORS, STYLESHEET = _load()

BG = COLORS["bg"]
BG_DEEP = COLORS["bg-deep"]
PANEL = COLORS["panel"]
PANEL_2 = COLORS["panel-hover"]
INPUT = COLORS["input"]
BORDER = COLORS["border"]
TEXT = COLORS["text"]
TEXT_BRIGHT = COLORS["text-bright"]
MUTED = COLORS["muted"]
ACCENT = COLORS["accent"]
ACCENT_2 = COLORS["accent-strong"]
GOLD = COLORS["gold"]
GREEN = COLORS["play-top"]
DANGER = COLORS["danger"]
