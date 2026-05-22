![DukeNano3D](DukeNano3D.jpg)

# DukeNano3D

Compact Duke Nukem 3D 1.3D Shareware `.grp` variants for constrained targets (for example `duke3d-go` in `retro-go` on ESP32-class devices).

## What this repo does

- Builds reduced-content `.grp` variants from the original shareware GRP.
- Optionally repacks assets (PNG optimization, audio conversion/compression) for smaller output.
- Produces ready-to-test variants for EDuke32 and embedded ports.

## Results

| Version | Size (KiB) | Reduction in % | Size Zipped (KiB) | Reduction in % |
| --- | --- | --- | --- | --- |
| DUKE3D_v1.3d_shareware.grp | 10777.1 | 0% | 4761.4 | 55.82% |
| E1L1-6.grp | 4011.1 | 62.78% | 2828.8 | 73.75% |
| E1L1-6_nearcomplete.grp | 3682.6 | 65.83% | 2533.1 | 76.50% |
| E1L1-6_compromise.grp | 3392.2 | 68.52% | 2268.6 | 78.95% |
| E1L1-6_tiny.grp | 3167.1 | 70.61% | 2077.4 | 80.72% |
| E1L1-2.grp | 2933.9 | 72.78% | 2286.9 | 78.78% |
| E1L1-3_nearcomplete.grp | 2931.9 | 72.79% | 2172.4 | 79.84% |
| E1L1-2_nearcomplete.grp | 2605.5 | 75.82% | 1990.6 | 81.53% |
| E1L1.grp | 2595.3 | 75.92% | 2044.7 | 81.03% |
| E1L1-2_compromise.grp | 2301.1 | 78.65% | 1723.6 | 84.01% |
| E1L1_compromise.grp | 1962.5 | 81.79% | 1479.3 | 86.27% |
| E1L1_tiny.grp | 1751.4 | 83.75% | 1291.6 | 88.02% |
| E1L1_minimal.grp | 1721.2 | 84.03% | 1267.2 | 88.24% |

Notes:

- Baseline is `input/DUKE3D_v1.3d_shareware.grp`.
- Both "Reduction in %" columns are compared to that same unzipped baseline.
- See `generate_variants.sh` for exact generation arguments used for named variants.
- Reusing a prepared PNG cache (`--temp-dir precalculated_pngs/ --keep-temp`, then `--pngfolder precalculated_pngs/`) significantly speeds up repeated runs.

### Regenerate the table

```bash
python3 compare_output_to_input_sizes.py
```

Optional custom paths:

```bash
python3 compare_output_to_input_sizes.py --input input/DUKE3D_v1.3d_shareware.grp --outputs outputs
```

## Requirements

Core:

- Python 3
- EDuke32 tooling: `kextract`, `kgroup`, `arttool`, `mapinfo`
- ImageMagick (`convert`)

Optional (depending on flags/workflow):

- `optipng` (for `--optipng`)
- `zopflipng` (for `--zopflipng`)
- `ffmpeg` (for `--adpcmwav` / `--adpcmwidth` workflows)
- `adpcm-xq` (for `--adpcmwidth`)
- `zip` (for `.grp.zip` output)

## Quick start

Build compact GRP variants:

```bash
python3 duke3d_compact_grp.py
```

Use scripted variant generation examples:

```bash
./compact.sh
./generate_variants.sh
```

Run a generated GRP in EDuke32 (example from `eduke32-for-DukeNano3D/runit.sh`):

```bash
./eduke32 -usecwd -g newfile.grp -l2
```

## How it works

`duke3d_compact_grp.py` performs the main pipeline:

- Extracts GRP content using EDuke32 `kextract`.
- Extracts tile data from `TILESNNN.ART` using `arttool`.
- Analyzes `.map` files to determine needed textures and MIDI files.
- Converts `.pcx` textures to `.png` with ImageMagick `convert`.
- Optionally optimizes PNGs with `optipng` and `zopflipng`.
- Converts `.voc` audio to `.wav` with `ffmpeg`.
- Optionally recompresses WAV to ADPCM via `adpcm-xq` (2-5 bit width).
- Rebuilds the final GRP with EDuke32 `kgroup`.

Optional zipped output uses:

```bash
zip -9 out.grp.zip out.grp
```

## Fork-specific notes

### EDuke32 fork

Already supports:

- PNG textures via `duke3d.def` [`definetexture`](https://wiki.eduke32.com/wiki/Tilefromtexture_(DEF))
- WAV sound effects via `duke3d.def` [`sound`](https://wiki.eduke32.com/wiki/Sound_(DEF))
- Tile range animation via `duke3d.def` [`animtilerange`](https://wiki.eduke32.com/wiki/Animtilerange_(DEF))

Added in this fork:

- ADPCM-compressed WAV sound effect support

### duke3d-go (retro-go branch)

Extended support includes:

- EDuke32-style PNG texture overrides
- EDuke32-style WAV sound effects
- EDuke32-style `animtilerange` handling
- ADPCM-compressed WAV sound effects

## Git submodule workflow

This repository tracks:

- `eduke32-for-DukeNano3D`
- `retro-go-for-DukeNano3D` (branch `Duke3D-with-fri3d-2026`)

Clone with submodules (recommended):

```bash
git clone --recursive https://github.com/ThomasFarstrike/DukeNano3D.git
```

If already cloned without `--recursive`:

```bash
git submodule update --init --recursive
```

Sync URL/config after `.gitmodules` updates:

```bash
git submodule sync --recursive
git submodule update --init --recursive
```

Update submodules to latest tracked remote commit:

```bash
git submodule update --remote --merge --recursive
```

Update one submodule only:

```bash
git submodule update --remote --merge eduke32-for-DukeNano3D
git submodule update --remote --merge retro-go-for-DukeNano3D
```

Commit updated submodule pointers in this superproject:

```bash
git add .gitmodules eduke32-for-DukeNano3D retro-go-for-DukeNano3D
git commit -m "Update submodules"
```

## Future work

### Excluding textures

1) Currently, all textures for a selected level set are included. If a required texture is missing, rendering artifacts appear (undrawn areas/"dragging"). One possible approach is to replace large textures with tiny placeholder PNGs (~200 bytes) that preserve dimensions and approximate average color. That could enable a future `--maxtexturesize` option similar to `--maxsoundsize`.

2) Some textures are not directly referenced in map sectors/walls but are still required (HUD, weapon sprites, kick animation, decorative animations). Better static analysis of `.con` game logic could identify what can safely be removed.

### Excluding sound effects

Current options:

- `--excludefiles` for explicit sound file exclusions
- `--maxsoundsize` to skip all sound files larger than a threshold

Future improvement: smarter `.map` + `.con` usage analysis to remove unused or rarely used `.voc` assets while preserving gameplay quality.
