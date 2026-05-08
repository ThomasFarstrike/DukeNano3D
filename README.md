# DukeNano3D
Tiny versions of Duke Nukem 3D GRP files, for devices with limited storage and RAM like duke3d-go in retro-go on the ESP32 microcontroller.

# Results

Version | Size in bytes | 

Original DUKE3D_v1.3d_shareware.grp | 11035779

## How to run

```
python3 duke3d_compact_grp.py
```

Also see compact.sh and generate_version.sh for example arguments.

## Work done

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
## Git submodule workflow (eduke32-for-DukeNano3D)

This repository tracks the EDuke32 fork as a Git submodule at `eduke32-for-DukeNano3D`.

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

### Update submodule to latest remote commit

To move the submodule to the latest commit on its tracked branch (typically `main`):

```bash
git submodule update --remote --merge eduke32-for-DukeNano3D
```

Then commit the updated submodule pointer in the superproject:

```bash
git add eduke32-for-DukeNano3D
git commit -m "Update eduke32-for-DukeNano3D submodule"
```
