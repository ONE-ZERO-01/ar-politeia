# Active Politeia simulation core

This directory is the versioned, active simulation source for AR-Politeia
Cycle 1. It was promoted from the immutable provenance snapshot at
`research/imports/politeia-ds/`; subsequent research changes are made only
here.

Cycle 1 adds independent terrain channels:

- `terrain_force_enabled` and `terrain_force_scale` control spatial motion;
- `terrain_production_enabled` and `terrain_production_scale` control local
  resource production.

The legacy `terrain_scale` key remains accepted and sets both scales for old
config compatibility. Confirmatory Cycle 1 configs must use the explicit
channel keys.

Numerical runs, including smoke tests, are executed only on `umi`. Local
machines may edit and compile the source but must not generate research
results.
