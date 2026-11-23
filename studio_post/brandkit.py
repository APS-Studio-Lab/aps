"""The channel's brand kit lives in Drive (<studio root>/00_Brand/brand.yaml), never in this repository.

The render farm downloads 00_Brand next to the repo before every job. Anything brand-specific (name, logo,
glossary of names the transcriber must spell right) comes from here, so the code stays brand-neutral.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from .util import REPO, StageError

KIT = REPO / "00_Brand"


@lru_cache(maxsize=1)
def load() -> dict:
    f = KIT / "brand.yaml"
    if not f.exists():
        return {}  # neutral output: no name, no logo
    data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise StageError(f"{f} must be a mapping")
    return data


def name() -> str:
    return str(load().get("name", ""))


def logo(on_dark: bool = True) -> Path | None:
    """The logo file. Video sits on dark sets, so the dark-background version is used when the kit has one
    (brand.yaml logo_dark, or logo/logo_primary_dark.png)."""
    k = load()
    if on_dark:
        for rel in (k.get("logo_dark"), "logo/logo_primary_dark.png"):
            if rel and (KIT / rel).exists():
                return KIT / rel
    rel = k.get("logo")
    if not rel:
        return None
    p = KIT / rel
    if not p.exists():
        raise StageError(f"brand kit logo not found: {p}")
    return p


def glossary() -> list[str]:
    return [str(x) for x in load().get("glossary", [])]
