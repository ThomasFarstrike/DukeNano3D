#!/usr/bin/env python3
"""Test all pipeline orders of pngquant, optipng, zopflipng on PCX->PNG tiles."""

import itertools
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

PCX_DIR = Path("precalculated_pngs_shareware_1.3D")
PALETTE = PCX_DIR / "palette.dat"

# Pick tiles spanning a range of sizes
TILE_PCX = [
    "tile0000.pcx",  # 2.5 KB  small
    "tile0090.pcx",  # 23 KB   large
    "tile2445.pcx",  # 62 KB   very large
]

ZOPFLI_ITERATIONS = 50  # fewer iterations for faster testing; same relative ranking

CONVERT = shutil.which("convert")
PNGQUANT = Path.home() / "software" / "pngquant"
OPTIPNG = shutil.which("optipng")
ZOPFLIPNG = shutil.which("zopflipng")

BASE_CONVERT_ARGS = [
    "-alpha", "on",
    "-transparent", "#FC00FC",
    "-strip",
    "-define", "png:compression-level=9",
    "-define", "png:compression-strategy=1",
    "-define", "png:exclude-chunks=date,time",
    "-colors", "256",
]

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
        "--quality", "10",
        "--speed", "1",
        "--posterize", "3",
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
    # single tools
    for n in names:
        all_pipelines[pipeline_name([n])] = [n]
    # pairs — both orders
    for a, b in itertools.permutations(names, 2):
        all_pipelines[pipeline_name([a, b])] = [a, b]
    # triples — all 6 orders
    for a, b, c in itertools.permutations(names, 3):
        all_pipelines[pipeline_name([a, b, c])] = [a, b, c]
    return all_pipelines

def main():
    for tool in [CONVERT, PNGQUANT, OPTIPNG, ZOPFLIPNG]:
        if not tool or (tool != CONVERT and tool != OPTIPNG and not Path(tool).exists()):
            print(f"ERROR: required tool not found: {tool}")
            sys.exit(1)
    if not PNGQUANT.exists():
        print(f"ERROR: pngquant not found at {PNGQUANT}")
        sys.exit(1)

    pipelines = build_pipelines()
    print(f"Testing {len(pipelines)} pipeline combinations across {len(TILE_PCX)} tiles\n")

    results = []

    for pcx_name in TILE_PCX:
        pcx_path = PCX_DIR / pcx_name
        if not pcx_path.exists():
            print(f"SKIP {pcx_name} — not found")
            continue

        base_size = pcx_path.stat().st_size
        print(f"\n{'='*70}")
        print(f"Tile: {pcx_name}  (PCX size: {base_size} bytes)")
        print(f"{'='*70}")

        for pname, steps in pipelines.items():
            with tempfile.TemporaryDirectory() as tmpdir:
                out_png = Path(tmpdir) / "tile.png"
                print(f"  [{pname:30s}] ", end="", flush=True)

                convert_cmd = [CONVERT, str(pcx_path)] + BASE_CONVERT_ARGS + [f"PNG8:{out_png}"]
                proc = run(convert_cmd, "convert")
                if proc.returncode != 0 or not out_png.exists():
                    print(f"CONVERT FAILED (skip)")
                    continue

                after_size = out_png.stat().st_size
                for step_name in steps:
                    TOOLS[step_name](out_png)
                    after_size = out_png.stat().st_size

                results.append({
                    "tile": pcx_name,
                    "pipeline": pname,
                    "final_bytes": after_size,
                    "savings_pct": (1 - after_size / base_size) * 100,
                })
                print(f"{after_size:>8,} bytes  ({results[-1]['savings_pct']:5.1f}%)")

    if not results:
        print("No results!")
        return

    print(f"\n{'='*70}")
    print("SUMMARY — Best pipeline per tile (smallest final bytes)")
    print(f"{'='*70}")
    tiles = sorted(set(r["tile"] for r in results))
    for tile in tiles:
        tile_results = [r for r in results if r["tile"] == tile]
        best = min(tile_results, key=lambda r: r["final_bytes"])
        worst = max(tile_results, key=lambda r: r["final_bytes"])
        print(f"  {tile}:")
        print(f"    BEST:  {best['pipeline']:30s}  {best['final_bytes']:>8,} bytes  ({best['savings_pct']:5.1f}%)")
        print(f"    WORST: {worst['pipeline']:30s}  {worst['final_bytes']:>8,} bytes  ({worst['savings_pct']:5.1f}%)")

    print(f"\n{'='*70}")
    print("AVERAGE RANKING (lowest average bytes = best)")
    print(f"{'='*70}")
    from collections import defaultdict
    pipe_totals = defaultdict(list)
    for r in results:
        pipe_totals[r["pipeline"]].append(r["final_bytes"])
    ranked = sorted(pipe_totals.items(), key=lambda kv: statistics.mean(kv[1]))
    for rank, (pname, sizes) in enumerate(ranked, 1):
        avg = statistics.mean(sizes)
        print(f"  {rank:2d}. {pname:30s}  avg {avg:>8,.0f} bytes")

    print(f"\n{'='*70}")
    print("BEST OVERALL (fewest total bytes across all tiles)")
    print(f"{'='*70}")
    pipe_totals2 = defaultdict(int)
    for r in results:
        pipe_totals2[r["pipeline"]] += r["final_bytes"]
    best_overall = min(pipe_totals2.items(), key=lambda kv: kv[1])
    print(f"  {best_overall[0]:30s}  {best_overall[1]:>8,} total bytes")

if __name__ == "__main__":
    main()
