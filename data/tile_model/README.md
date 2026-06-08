# Tile Model CSVs

These CSVs define runtime tile modeling rules used by `duke3d_compact_grp.py`.

Files:

- `tile_spans.csv`
  - `category=sprite_precache`: trigger tile implies contiguous `trigger..trigger+length-1`
  - `category=spawn_span`: spawned base tile implies contiguous runtime span
- `tile_transitions.csv`
  - Explicit trigger->include mappings (state replacements and spawn whitelist rules)
- `tile_baselines.csv`
  - Baseline includes for `runtime_essential` and `menu_ultra`

Token syntax:

- Single: `RAT` or `1267`
- Relative: `RAT+4`, `SHRINKER-2`
- Range: `RAT..RAT+4`, `2504..2506`
- Multi-value list: `A|B|C`

Notes:

- Symbolic names resolve through CON defines loaded from extracted `.CON` files.
- Unknown names are ignored, so CSVs can be shared across close variants.
