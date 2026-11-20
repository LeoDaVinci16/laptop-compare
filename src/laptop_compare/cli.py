"""Command line: `laptop-compare --data data --base "HP ProBook 4 G1i 14 (current)"`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .compare import compare
from .data import DataFileError, load_dataset
from .validate import ERROR, find_issues

FORMATS = ("html", "qmd", "md")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="laptop-compare",
        description="Compare laptops spec by spec against a base laptop. "
                    "Writes comparison CSVs, plots and a report.")
    p.add_argument("--data", default="data", type=Path,
                   help="folder with laptops.csv, specs.csv and ranks/ (default: data)")
    p.add_argument("--base", help="laptop to compare against (exact name; default: first row of laptops.csv)")
    p.add_argument("--out", default="output", type=Path, help="output folder (default: output)")
    p.add_argument("--format", nargs="+", choices=FORMATS, default=["html", "qmd"],
                   help="report formats (default: html qmd)")
    p.add_argument("--csv-sep", default=",", help="separator for the output CSVs (use ';' for Excel in Spain)")
    p.add_argument("--no-plots", action="store_true", help="skip the charts (faster)")
    p.add_argument("--list", action="store_true", help="list the laptops and exit")
    p.add_argument("--check", action="store_true", help="only check the data for problems and exit")
    p.add_argument("--strict", action="store_true", help="stop with an error if the data has problems")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        ds = load_dataset(args.data)
    except FileNotFoundError as e:
        print(f"Could not find a data file: {e.filename}\n"
              f"Check that --data points to the folder with laptops.csv and specs.csv.", file=sys.stderr)
        return 2
    except DataFileError as e:
        print(f"Problem in the data: {e}", file=sys.stderr)
        return 2

    if args.list:
        for i, name in enumerate(ds.names, 1):
            print(f"{i:>3}. {name}")
        return 0

    issues = find_issues(ds)
    if issues:
        print(f"Found {len(issues)} thing(s) to fix in the data:\n")
        for issue in issues:
            print(issue)
        print()
    else:
        print("✅ Data OK: every spec has a type and every ranked value has a rank.")
    if args.check:
        return 1 if any(i.level == ERROR for i in issues) else 0
    if args.strict and any(i.level == ERROR for i in issues):
        print("Stopping because of --strict.", file=sys.stderr)
        return 1

    base = args.base or ds.names[0]
    if base not in ds.names:
        matches = [n for n in ds.names if base.lower() in n.lower()]
        if len(matches) == 1:
            base = matches[0]
        else:
            print(f"Base '{base}' not found. Use --list to see the names.", file=sys.stderr)
            return 2

    comp = compare(ds, base)
    out = args.out
    out.mkdir(parents=True, exist_ok=True)

    from .report import write_csvs, write_html, write_markdown

    written = write_csvs(ds, comp, out, sep=args.csv_sep)
    plots: dict = {}
    if not args.no_plots:
        from .plots import make_all

        plots = make_all(ds, comp, out)
    if "html" in args.format:
        written.append(write_html(ds, comp, issues, plots, out / "report.html"))
    if "qmd" in args.format:
        written.append(write_markdown(ds, comp, issues, plots, out / "report.qmd", quarto=True))
    if "md" in args.format:
        written.append(write_markdown(ds, comp, issues, plots, out / "report.md", quarto=False))

    n_plots = (1 if plots.get("overview") else 0) + len(plots.get("specs", {})) + len(plots.get("laptops", {}))
    print(f"Base: {base}")
    for p in written:
        print(f"  wrote {p}")
    if n_plots:
        print(f"  wrote {n_plots} charts in {out / 'plots'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
