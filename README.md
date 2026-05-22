
![DukeNano3D](DukeNano3D.jpg)

# DukeNano3D
Tiny versions of Duke Nukem 3D 1.3D Shareware GRP files, for devices with limited storage and RAM like duke3d-go in retro-go on the ESP32 microcontroller.

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

- Original file is the official Duke Nukem 1.3D Shareware, and all "reduction in %" are compared to that original.
- See `generate_variants.sh` for the exact arguments provided.
- To save time, the optimized PNGs were created once with `--temp-dir precalculated_pngs/ --keep-temp` (takes around 4 hours) and then reused each time with `--pngfolder precalculated_pngs/`

## Required tools

Core:

- Python 3
- EDuke32 tooling: `kextract`, `kgroup`, `arttool`, `mapinfo`
- ImageMagick `convert`

Optional (depending on flags/workflow):

- `optipng` (for `--optipng`)
- `zopflipng` (for `--zopflipng`)
- `ffmpeg` (for `--adpcmwav` / `--adpcmwidth` workflows)
- `adpcm-xq` (for `--adpcmwidth`)
- `zip` (for making `.grp.zip` files)

## How to run

Build compact GRP variants:

```bash
python3 duke3d_compact_grp.py
```

Run the generated GRP in EDuke32 (from `eduke32-for-DukeNano3D/runit.sh`):

```bash
./eduke32 -usecwd -g newfile.grp -l2
```

Also see compact.sh and generate_variants.sh for example arguments.

## How it works

The actual work of compressing a GRP file is done by `duke3d_compact_grp.py` which includes:

- extracting GRP file using EDuke32's kextract
- extracting TILESNNN.ART files using EDuke32's arttool
- analysing .MAP files to find out which textures and .MID(i) files it needs
- converting .pcx texture images to .png using Imagemagick's `convert`
- compressing .png files using `optipng` and `zopflipng`
- converting .VOC (raw PCM audio) to .WAV files using `ffmpeg`
- converting .WAV files to ADPCM-compressed .WAV files using adpcm-xq (which supports 2 to 5-bit width)
- bundling the files into a new GRP file using EDuke32's kgroup

Optional Zipping of the .grp file is done with a simple `zip -9 out.grp.zip out.grp`

### EDuke32 fork

- already supports PNG textures (duke3d.def `[definetexture](https://wiki.eduke32.com/wiki/Tilefromtexture_(DEF))`)
- already supports WAV sound effects (duke3d.def `[sound](https://wiki.eduke32.com/wiki/Sound_(DEF))`)
- already supports anim(ations) from tile ranges (duke3d.def `[animtilerange](https://wiki.eduke32.com/wiki/Animtilerange_(DEF))`)

- didn't support ADPCM compressed WAV sound effects => added this

###  duke3d-go

The duke3d-go on an experimental branch of retro-go was extended to support:

- EDuke32-style PNG texture override
- EDuke32-style WAV sound effects
- EDuke32-style anim(ations) from tile ranges (duke3d.def `[animtilerange](https://wiki.eduke32.com/wiki/Animtilerange_(DEF))`) => added this
- ADPCM compressed WAV sound effects
-
## Git submodule workflow

This repository tracks the following Git submodules:

- `eduke32-for-DukeNano3D`
- `retro-go-for-DukeNano3D` (tracks branch `Duke3D-with-fri3d-2026`)

### Clone with submodules (recommended)

```bash
git clone --recursive https://github.com/ThomasFarstrike/DukeNano3D.git
```

If you already cloned without `--recursive`:

```bash
git submodule update --init --recursive
```

### Sync submodule URLs/config from `.gitmodules`

Run this if `.gitmodules` changed (for example, after upstream URL updates):

```bash
git submodule sync --recursive
git submodule update --init --recursive
```

### Update submodules to latest remote commit on their tracked branches

To move all submodules to the latest commit of their tracked branch:

```bash
git submodule update --remote --merge --recursive
```

Or update only one submodule:

```bash
git submodule update --remote --merge eduke32-for-DukeNano3D
git submodule update --remote --merge retro-go-for-DukeNano3D
```

Then commit updated submodule pointers in the superproject:

```bash
git add .gitmodules eduke32-for-DukeNano3D retro-go-for-DukeNano3D
git commit -m "Update submodules"
```

## Future work

### Excluding textures

1) Currently, all the textures of a level are included, because if a texture is is missing, you get an ugly visual "dragging" effect because that area of the screen is not being drawn. But this could be avoided by replacing the texture with a minimal PNG (~200 bytes) that has the correct size and average color of the texture. This would allow a `--maxtexturesize` option to be created, similar to the existing `--maxsoundsize` option. Even a tiny `--maxtexturesize 300` would probably result in a game that's still playable, just less interesting.

2) A lot of textures are not defined in the map but are still used, such as the heads up display textures, the weapons, the boot kick animation, and lots of animations such as the 'ladies', dollar bills etc. Currently, these are all included, even if the included map(s) don't actually use those textures. Smarter (or manual) analysis of the .CON game logic scripts would allow excluding those.

### Excluding sound effects

Currently, there's an option `--excludefiles` to exclude specific sound effect files that are known to be large, or `--maxsoundsize` to exclude all sound effect files bigger than N bytes.

But smarter (or manual) .MAP or .CON analysis would allow excluding .VOC files that aren't used in the included maps, or that are rarely used (like some Duke quotes).
