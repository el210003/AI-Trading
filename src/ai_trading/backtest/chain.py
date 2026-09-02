"""BT-01 single-pass chain runner — THE shared code path with live analysis.

The replay engine runs the identical Phase 2 detector chain ONCE over the
loaded range and consumes outputs through the as-of slicer. BT-01 requires
these exact exported functions — detect_swings, build_zigzag, detect_pools,
derive_zones, htf_context — never a re-implementation for speed (a second
implementation = drifted rules = invalid labels).

Composition mirrors the verified integration composition (Phase 2
test_detector_integration.run_chain): M15 swings -> zigzag -> pools (+
events); H1/H4 swings -> zigzag -> zones; htf_context joins both onto M15.

Pure: zero file I/O, zero MetaTrader5 imports, input frames never mutated.
"""

from __future__ import annotations

import pandas as pd

from ai_trading.detectors.mtf import htf_context
from ai_trading.detectors.pools import detect_pools
from ai_trading.detectors.swings import detect_swings
from ai_trading.detectors.zigzag import build_zigzag
from ai_trading.detectors.zones import derive_zones

M15 = "M15"
H1 = "H1"
H4 = "H4"


def run_chain(m15: pd.DataFrame, h1: pd.DataFrame, h4: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Run the production detector chain over the loaded frames and return
    the dict of tier outputs keyed: swings15, zigzag15, pools15, events15,
    swings_h1, zigzag_h1, zones_h1, swings_h4, zigzag_h4, zones_h4, payload.
    """
    swings15 = detect_swings(m15, M15)
    zigzag15 = build_zigzag(swings15)
    pools15, events15 = detect_pools(m15, swings15)
    swings_h1 = detect_swings(h1, H1)
    zigzag_h1 = build_zigzag(swings_h1)
    zones_h1 = derive_zones(zigzag_h1, h1)
    swings_h4 = detect_swings(h4, H4)
    zigzag_h4 = build_zigzag(swings_h4)
    zones_h4 = derive_zones(zigzag_h4, h4)
    payload = htf_context(m15, zones_h1, zones_h4)
    return {
        "swings15": swings15,
        "zigzag15": zigzag15,
        "pools15": pools15,
        "events15": events15,
        "swings_h1": swings_h1,
        "zigzag_h1": zigzag_h1,
        "zones_h1": zones_h1,
        "swings_h4": swings_h4,
        "zigzag_h4": zigzag_h4,
        "zones_h4": zones_h4,
        "payload": payload,
    }
