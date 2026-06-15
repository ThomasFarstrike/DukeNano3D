# DukeNano3D Agent Notes

## Scope and Layout
- Root repo is a GRP-compaction workspace; most firmware/engine code lives in git submodules.
- `eduke32-for-DukeNano3D/` provides required command-line tools used by `duke3d_compact_grp.py` (`kextract`, `kgroup`, `arttool`, `mapinfo`).
- `retro-go-for-DukeNano3D/` is the ESP-IDF firmware tree (target branch in `.gitmodules`: `Duke3D-with-fri3d-2026`).

## Primary Commands (root)
- Build one compacted GRP: `python3 duke3d_compact_grp.py input/DUKE3D_v1.3d_shareware.grp`.
- Build the predefined variant set: `bash generate_variants.sh` (writes `.grp` and `.grp.zip` into `outputs/`).
- Recompute README size table: `python3 compare_output_to_input_sizes.py`.

## Compactor Script Gotchas (`duke3d_compact_grp.py`)
- The positional `grpfile` argument is required; scripts usually pass `input/DUKE3D_v1.3d_shareware.grp`.
- Tool discovery is repo-local first: it looks for executables in `./` and `./eduke32-for-DukeNano3D/` before PATH.
- `--adpcmwidth` only works with `--adpcmwav`, and uses a hardcoded binary path: `/home/user/sources/adpcm-xq/adpcm-xq`.
- Temp cleanup is aggressive: it always deletes `./temp_folder` at start, even if `--temp-dir` points elsewhere.
- If `--pngfolder` is used, `--optipng` and `--zopflipng` are intentionally ignored.
- ART file format (shareware): `version(4B) | numtiles(4B) | start_tile(4B) | end_tile(4B) | widths(2B*N) | heights(2B*N) | picanm(4B*N) | pixel_data`.
  `arttool` always writes `numtiles=0` on rewrite; the reader ignores it. Always use `start_tile`/`end_tile` to get the tile range.
- `--onlysmaller` includes empty-ART removal: after the cleanup pass, files with zero `width*height>0` tiles are deleted from temp_dir.
- Per-file overhead: when PNG-total for a file's tiles is smaller than the ART file, it may be worth converting all tiles to PNG and dropping ART. Currently only empty files (0 non-empty tiles) are dropped, not "sparse" ones.

## Building Required EDuke32 Tools
- From `eduke32-for-DukeNano3D/`, run `make tools` to build `kextract`, `kgroup`, `arttool`, and `mapinfo` (these are explicit GNUmakefile tool targets).
- `eduke32-for-DukeNano3D/build.sh` installs Linux deps (`libflac-dev`, `libvpx-dev`) and builds with `make RELEASE=0`.

## Retro-Go / ESP-IDF Notes (submodule)
- `retro-go-for-DukeNano3D/AGENTS.md` requires sourcing ESP-IDF env before compile/gdb/addr2line:
  `. ~/projects/MicroPythonOS/claude/MicroPythonOS/lvgl_micropython/lib/esp-idf/export.sh`
- `retro-go-for-DukeNano3D/rg_tool.py` hard-fails if `IDF_PATH` is unset; always run inside exported ESP-IDF environment.
- Project scripts target `fri3d-2024`/`fri3d-2026`; a common build is:
  `./rg_tool.py --target fri3d-2026 build retro-core duke3d-go`
- Some helper scripts patch the global ESP-IDF file `.../components/esp_driver_sdspi/src/sdspi_host.c` via `sed -i`; treat those scripts as machine-specific and potentially destructive.

## Working Practices
- Do not assume a clean tree: this repo commonly has large generated/untracked artifacts (`outputs/`, `precalculated_pngs/`, `*.grp`, `littlefs2.bin`, etc.). Avoid deleting them unless explicitly asked.
- Keep superproject and submodule work separate; if submodule pointers changed, confirm that was intentional before committing.
