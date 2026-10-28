"""
Pyrofuel v3 — Institutional Microstructure, Derivatives, & Frontier Alpha Features Package.

Uses lazy module resolution (`__getattr__`) so sub-modules (including `regime` owned by
`A-STRAT` and microstructure/frontier modules owned by `A-DATA-MICRO`) can be imported
independently without circular or startup import collisions.
"""

from __future__ import annotations

import importlib
from typing import Any

__all__ = [
    "microstructure",
    "orthogonal",
    "toxicity",
    "hawkes",
    "spot_perp_leadlag",
    "fracdiff_kyle",
    "cross_asset_leadlag",
    "liq_heatmap",
    "options_surface",
    "spoof_iceberg",
    "global_radar",
    "hyperliquid_radar",
    "path_signatures",
    "macro_funding_shield",
]


def __getattr__(name: str) -> Any:
    if name in __all__ or name == "regime":
        return importlib.import_module(f".{name}", __name__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
