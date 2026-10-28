"""
Pyrofuel v3 — Real-Time Data & Closed-Bar Integrity Package (Pilar 1 / T3.1).
"""

from .stream import (
    BinanceFuturesStreamManager,
    compute_forming_volume_pace,
    separate_closed_and_forming_klines,
)

__all__ = [
    "BinanceFuturesStreamManager",
    "compute_forming_volume_pace",
    "separate_closed_and_forming_klines",
]
