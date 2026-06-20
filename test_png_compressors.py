#!/usr/bin/env python3
"""Test all pipeline orders of pngquant, optipng, zopflipng on PCX->PNG tiles."""

import itertools
import shutil
import statistics
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

from duke3d_compact_grp import convert_pcx_to_png8

PCX_DIR = Path("precalculated_pngs_shareware_1.3D")

TILE_PCX = [
    "tile0000.pcx",  # 2.5 KB  small
    "tile0090.pcx",  # 23 KB   large
    "tile2445.pcx",  # 62 KB   very large
]

ZOPFLI_ITERATIONS = 50
OUTPUT_DIR = Path("png_test_outputs")

PNGQUANT = Path.home() / "software" / "pngquant"
OPTIPNG = shutil.which("optipng")
ZOPFLIPNG = shutil.which("zopflipng")

# Pre-existing PNGs for comparison
PNG_DIRS = {
    "shareware": Path("precalculated_pngs_shareware_1.3D"),
    "pngquant": Path("precalculated_pngs_pngquant"),
    "pngquant_10": Path("precalculated_pngs_pngquant_10"),
}


def run(cmd, desc=""):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode not in (0, 99):
        print(f"  [ERROR] {desc} exited {proc.returncode}: {cmd}")
        if proc.stderr:
            print(f"  stderr: {proc.stderr[:300]}")
    return proc

def apply_pngquant(png_path):
    return run([
        str(PNGQUANT),
        "--quality", "69-71",
        "--speed", "1",
        "--posterize", "2",
        "--ext", ".PNG",
        "--force",
        str(png_path),
    ], "pngquant")

def apply_optipng(png_path):
    return run([OPTIPNG, "-o7", str(png_path)], "optipng")

def apply_zopflipng(png_path):
    return run([
        ZOPFLIPNG,
        f"--iterations={ZOPFLI_ITERATIONS}",
        "--filters=01234mepb",
        "--lossy_8bit",
        "--lossy_transparent",
        "-y",
        str(png_path),
        str(png_path),
    ], "zopflipng")

TOOLS = {
    "pngquant": apply_pngquant,
    "optipng": apply_optipng,
    "zopflipng": apply_zopflipng,
}

def pipeline_name(seq):
    return "+".join(seq)

def build_pipelines():
    names = list(TOOLS.keys())
    all_pipelines = {}
    for n in names:
        all_pipelines[pipeline_name([n])] = [n]
    for a, b in itertools.permutations(names, 2):
        all_pipelines[pipeline_name([a, b])] = [a, b]
    #for a, b, c in itertools.permutations(names, 3):
        #all_pipelines[pipeline_name([a, b, c])] = [a, b, c]
    return all_pipelines

def get_colors(png_path):
    try:
        out = subprocess.run(
            ["identify", "-verbose", str(png_path)],
            capture_output=True, text=True
        ).stdout
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("Colors:"):
                return int(line.split(":")[1].strip())
    except Exception:
        return None
    return None

def find_prebuilt(tile_num):
    num = f"TILE{tile_num:04d}.PNG"
    results = {}
    for label, d in PNG_DIRS.items():
        p = d / num
        if p.exists():
            results[label] = p.stat().st_size
    return results

def main():
    for tool in [PNGQUANT, OPTIPNG, ZOPFLIPNG]:
        if not tool or not Path(str(tool)).exists():
            print(f"ERROR: required tool not found: {tool}")
            sys.exit(1)

    pipelines = build_pipelines()
    print(f"Testing {len(pipelines)} pipeline combinations across {len(TILE_PCX)} tiles\n")

    results = []

    for pcx_name in TILE_PCX:
        pcx_path = PCX_DIR / pcx_name
        if not pcx_path.exists():
            print(f"SKIP {pcx_name}")
            continue

        tile_num = int(pcx_name.replace("tile", "").replace(".pcx", ""))
        base_size = pcx_path.stat().st_size
        prebuilt = find_prebuilt(tile_num)

        tile_stem = pcx_name.replace(".pcx", "")
        out_dir = OUTPUT_DIR / tile_stem
        out_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n{'='*70}")
        print(f"Tile: {pcx_name}  (PCX: {base_size} bytes)")
        if prebuilt:
            print(f"  Pre-existing PNGs: " + ", ".join(f"{k}={v}B" for k, v in prebuilt.items()))
        print(f"{'='*70}")

        # Baseline: palette-preserving PCX -> PNG conversion
        out_png = out_dir / "convert-only.PNG"
        try:
            convert_pcx_to_png8(pcx_path, out_png)
            sz = out_png.stat().st_size
            cols = get_colors(out_png)
            print(f"  {'convert-only':30s}  {sz:>8,} bytes  colors={cols}")
            results.append({
                "tile": pcx_name, "pipeline": "convert-only",
                "final_bytes": sz, "colors": cols,
                "savings_pct": (1 - sz / base_size) * 100,
            })
        except Exception as e:
            print(f"  [convert-only] conversion failed: {e}")

        for pname, steps in pipelines.items():
            out_png = out_dir / f"{pname}.PNG"
            try:
                convert_pcx_to_png8(pcx_path, out_png)
            except Exception as e:
                print(f"  [{pname:30s}] CONVERT FAILED: {e}")
                continue

            for step_name in steps:
                TOOLS[step_name](out_png)

            sz = out_png.stat().st_size
            cols = get_colors(out_png)
            results.append({
                "tile": pcx_name, "pipeline": pname,
                "final_bytes": sz, "colors": cols,
                "savings_pct": (1 - sz / base_size) * 100,
            })
            print(f"  {pname:30s}  {sz:>8,} bytes  colors={cols!s:>4}  ({results[-1]['savings_pct']:5.1f}%)")

    if not results:
        print("No results!")
        return

    print(f"\n{'='*70}")
    print("BEST PER TILE (smallest)")
    print(f"{'='*70}")
    for tile in sorted(set(r["tile"] for r in results)):
        tile_results = [r for r in results if r["tile"] == tile]
        best = min(tile_results, key=lambda r: r["final_bytes"])
        worst = max(tile_results, key=lambda r: r["final_bytes"])
        print(f"  {tile}:")
        print(f"    BEST:  {best['pipeline']:30s}  {best['final_bytes']:>8,} B  colors={best['colors']}")
        print(f"    WORST: {worst['pipeline']:30s}  {worst['final_bytes']:>8,} B  colors={worst['colors']}")

    print(f"\n{'='*70}")
    print("AVERAGE RANKING (lowest avg bytes = best)")
    print(f"{'='*70}")
    pipe_totals = defaultdict(list)
    for r in results:
        pipe_totals[r["pipeline"]].append(r["final_bytes"])
    ranked = sorted(pipe_totals.items(), key=lambda kv: statistics.mean(kv[1]))
    for rank, (pname, sizes) in enumerate(ranked, 1):
        avg = statistics.mean(sizes)
        print(f"  {rank:2d}. {pname:30s}  avg {avg:>8,.0f} B")

    print(f"\n{'='*70}")
    print("TOTAL BYTES (lower = better)")
    print(f"{'='*70}")
    pipe_totals2 = defaultdict(int)
    for r in results:
        pipe_totals2[r["pipeline"]] += r["final_bytes"]
    for pname, total in sorted(pipe_totals2.items(), key=lambda kv: kv[1]):
        print(f"  {pname:30s}  {total:>8,} B")

if __name__ == "__main__":
    main()
