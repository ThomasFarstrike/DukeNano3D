#!/usr/bin/env python3

import argparse
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare output GRP sizes against original input GRP size."
    )
    parser.add_argument(
        "--input",
        default="input/DUKE3D_v1.3d_shareware.grp",
        help="Path to original input GRP file.",
    )
    parser.add_argument(
        "--outputs",
        default="outputs",
        help="Directory containing output .grp and .grp.zip files.",
    )
    return parser.parse_args()


def kib(path: Path) -> float:
    return path.stat().st_size / 1024.0


def pct_reduction(value_kib: float, baseline_kib: float) -> float:
    return (1.0 - (value_kib / baseline_kib)) * 100.0


def main() -> int:
    args = parse_args()

    input_path = Path(args.input)
    outputs_dir = Path(args.outputs)

    if not input_path.is_file():
        raise SystemExit(f"Input file not found: {input_path}")
    if not outputs_dir.is_dir():
        raise SystemExit(f"Outputs directory not found: {outputs_dir}")

    input_kib = kib(input_path)

    rows = []
    for grp_path in outputs_dir.glob("*.grp"):
        zip_path = Path(str(grp_path) + ".zip")
        if not zip_path.is_file():
            continue

        grp_kib = kib(grp_path)
        zip_kib = kib(zip_path)

        rows.append(
            {
                "name": grp_path.name,
                "grp_kib": grp_kib,
                "grp_reduction": pct_reduction(grp_kib, input_kib),
                "zip_kib": zip_kib,
                "zip_reduction": pct_reduction(zip_kib, input_kib),
            }
        )

    rows.sort(key=lambda row: row["grp_kib"], reverse=True)

    print("| Version | Size (KiB) | Reduction in % | Size Zipped (KiB) | Reduction in % |")
    print("| --- | --- | --- | --- | --- |")
    input_zip_path = Path(str(input_path) + ".zip")
    if input_zip_path.is_file():
        input_zip_kib = kib(input_zip_path)
        input_zip_reduction = pct_reduction(input_zip_kib, input_kib)
        input_zip_size_cell = f"{input_zip_kib:.1f}"
        input_zip_reduction_cell = f"{input_zip_reduction:.2f}%"
    else:
        input_zip_size_cell = "-"
        input_zip_reduction_cell = "-"

    print(
        f"| {input_path.name} | {input_kib:.1f} | 0% | "
        f"{input_zip_size_cell} | {input_zip_reduction_cell} |"
    )

    for row in rows:
        print(
            f"| {row['name']} | {row['grp_kib']:.1f} | {row['grp_reduction']:.2f}% | "
            f"{row['zip_kib']:.1f} | {row['zip_reduction']:.2f}% |"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
