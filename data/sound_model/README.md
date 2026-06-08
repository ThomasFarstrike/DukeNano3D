# Sound Model CSVs

These CSVs define runtime sound dependency rules used by `duke3d_compact_grp.py`.

Files:

- `sound_baselines.csv`
  - `category=runtime_essential`: baseline sounds always kept for map-driven compactions.
- `sound_transitions.csv`
  - Trigger/context -> include mappings for map/runtime sound closure.

Token syntax:

- Single: `SHOTGUN_FIRE` or `109`
- Relative: `BOS1_ROAM+1`, `KICK_HIT-1`
- Range: `BOS1_ROAM..BOS1_ROAM+4`, `100..110`
- Multi-value list: `A|B|C`

`sound_transitions.csv` columns:

- `category`: grouping label for debug/dumps.
- `trigger_type`: one of:
  - `always`
  - `tile_present` (checks final required tile set)
  - `map_sprite_pic`
  - `map_sprite_lotag`
  - `map_sprite_hitag`
  - `map_sector_lotag`
  - `map_wall_lotag`
- `trigger`:
  - token list/ranges for most trigger types
  - `*` means "all values observed in that context"
- `include`:
  - token list/ranges (static includes), or
  - `@trigger_value` (include numeric trigger value as sound ID), or
  - `@trigger_value_minus_10000` (include trigger-10000 as sound ID)

Notes:

- Symbolic names resolve through CON defines loaded from extracted `.CON` files.
- Unknown names are ignored so CSVs stay portable across close game/script variants.
