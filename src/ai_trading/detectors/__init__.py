"""Pure SMC detector transforms: no adapter-tier vendor-package imports, no
file I/O, no state. Every module is a pure DataFrame/Series -> DataFrame/Series
function unit-testable without the MetaTrader5 terminal (ROADMAP SC5).

Package layout (Phase 2): atr (Wilder ATR), swings (confirmation-shifted
2/2 fractal swings, D-01..D-03), zigzag (alternating canonical structure,
D-04), pools, zones, mtf. Import submodules directly — this file stays a
bare marker for the whole of Phase 2.
"""
