"""Write the outputs: comparison CSVs, an HTML report (single file) and a Quarto/Markdown report."""

from __future__ import annotations

import json
import math
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
from jinja2 import Environment, PackageLoader, select_autoescape

from .compare import EMPTY, MISSING, Comparison, best_per_spec, goodness
from .data import INFO, Dataset
from .validate import Issue

# --------------------------------------------------------------------------- CSV


def write_csvs(ds: Dataset, comp: Comparison, out_dir: Path, sep: str = ",") -> list[Path]:
    """comparison.csv (what you read), comparison_ratios.csv / comparison_verdicts.csv (numbers to reuse),
    scores_0_100.csv (heatmap values)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "comparison.csv": comp.frame("text"),
        "comparison_ratios.csv": comp.frame("ratio"),
        "comparison_verdicts.csv": comp.frame("verdict"),
        "scores_0_100.csv": goodness(ds).round(1),
    }
    paths = []
    for name, df in files.items():
        df = df.copy()
        df.insert(0, "Is base", ["yes" if n == comp.base else "" for n in df.index])
        path = out_dir / name
        df.to_csv(path, sep=sep, encoding="utf-8-sig")
        paths.append(path)
    return paths


# --------------------------------------------------------------------------- shared pieces

def _css_class(cell) -> str:
    if cell.status == MISSING:
        return "missing"
    if cell.status == EMPTY or math.isnan(cell.verdict):
        return ""
    return "better" if cell.verdict > 0 else "worse" if cell.verdict < 0 else ""


def _value_text(v) -> str:
    if isinstance(v, float):
        return "" if math.isnan(v) else f"{v:,.2f}".rstrip("0").rstrip(".")
    return str(v)


def _laptop_facts(ds: Dataset, name: str) -> list[tuple[str, str]]:
    """Key facts for a laptop section, plus the details stored in the rank files (e.g. CPU info)."""
    facts = []
    for col in ds.laptops.columns:
        v = _value_text(ds.laptops.at[name, col])
        if not v:
            continue
        table = ds.ranks.get(col)
        if table is not None and table.has(v) and table.details(v):
            v = f"{v} — {table.details(v)}"
        facts.append((col, v))
    return facts


def _value_columns(ds: Dataset) -> list[str]:
    """Spec values table: every column except long free text (notes), which goes in each laptop's section."""
    def long_text(col) -> bool:
        return ds.laptops[col].astype(str).str.len().max() > 40
    return [c for c in ds.laptops.columns
            if not (c in ds.specs and ds.specs[c].compare == INFO and long_text(c))]


def _display_specs(ds: Dataset, comp: Comparison) -> list[str]:
    """Comparison table columns: compared specs first; long info columns (notes, shop) left out."""
    return [s for s in comp.specs if s in ds.specs and ds.specs[s].compare != INFO]


# --------------------------------------------------------------------------- HTML

def _num(v):
    """float -> JSON-safe number (NaN becomes null)."""
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else round(float(v), 4)


def _heat_color(v: float) -> str:
    """0–100 -> red/yellow/green background (same colours as the PNG heatmap)."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "#EEEEEE"
    import matplotlib

    r, g, b, _ = matplotlib.colormaps["RdYlGn"](v / 100 * 0.8 + 0.1)   # avoid the darkest ends
    return "#{:02x}{:02x}{:02x}".format(int(r * 255), int(g * 255), int(b * 255))


def report_data(ds: Dataset, base: str) -> dict:
    """Everything the interactive HTML needs, with the comparison precomputed for EVERY possible base,
    so the report can switch base in the browser without Python."""
    from .compare import compare as run_compare, quantity, uses_score
    from .data import HIGHER, LOWER, RANKED

    compared = [s for s in ds.columns(HIGHER, LOWER, RANKED)]
    comp = {}
    for b in ds.names:
        c = run_compare(ds, b)
        comp[b] = {n: {s: [c.cells[(n, s)].text, _num(c.cells[(n, s)].verdict), _num(c.cells[(n, s)].ratio),
                           c.cells[(n, s)].status] for s in compared} for n in ds.names}

    charted, quantities = [], {}
    for s in compared:
        q = quantity(ds, s)
        if q.notna().sum() == 0:
            continue
        quantities[s] = {n: _num(q[n]) for n in ds.names}
        spec = ds.specs[s]
        entry = {"name": s, "compare": spec.compare, "ranked": spec.compare == RANKED,
                 "usesScore": uses_score(ds, s), "tiers": []}
        if spec.compare == RANKED and not entry["usesScore"]:
            table = ds.ranks[s].table
            worst = table["rank"].max()
            for r in sorted(table["rank"].dropna().unique()):
                entry["tiers"].append({"tier": float(worst - r + 1),
                                       "label": " / ".join(table.index[table["rank"] == r])})
        charted.append(entry)

    g = goodness(ds)
    return {
        "laptops": ds.names, "defaultBase": base, "compared": compared, "comp": comp,
        "charted": charted, "specByName": {e["name"]: e for e in charted} | {
            s: {"name": s, "compare": ds.specs[s].compare} for s in compared if s not in quantities},
        "quantity": quantities,
        "values": {n: {s: _value_text(ds.laptops.at[n, s]) for s in ds.laptops.columns} for n in ds.names},
        "goodnessSpecs": list(g.columns),
        "goodness": {s: {n: _num(g.at[n, s]) for n in ds.names} for s in g.columns},
        "facts": {n: _laptop_facts(ds, n) for n in ds.names},
    }


def write_html(ds: Dataset, comp: Comparison, issues: list[Issue], plots: dict | None, path: Path) -> Path:
    """Interactive single-file report: pick the base laptop in the page and everything is redrawn.
    The charts are drawn by the browser (no PNGs, no internet needed)."""
    env = Environment(loader=PackageLoader("laptop_compare", "templates"), autoescape=select_autoescape())
    tpl = env.get_template("report.html.j2")

    value_specs = _value_columns(ds)
    value_rows = []
    for n in comp.laptops:
        cells = []
        for s in value_specs:
            text = _value_text(ds.laptops.at[n, s])
            is_text = not re.fullmatch(r"[\d.,]*", text)
            cls = "missing" if comp.cells[(n, s)].status == MISSING else ("text" if is_text and s in ds.specs
                                                                           and ds.specs[s].compare == INFO else "")
            cells.append({"text": text, "cls": cls})
        value_rows.append({"name": n, "cells": cells})

    g = goodness(ds)
    heat = {"specs": list(g.columns),
            "rows": [{"name": n, "cells": [{"text": "" if math.isnan(g.at[n, s]) else f"{g.at[n, s]:.0f}",
                                            "bg": _heat_color(g.at[n, s])} for s in g.columns]} for n in ds.names]}

    data = report_data(ds, comp.base)
    html = tpl.render(
        base=comp.base, laptops=ds.names, n_laptops=len(ds.names), n_specs=len(ds.laptops.columns),
        generated=datetime.now().strftime("%Y-%m-%d %H:%M"), data_dir=str(ds.data_dir),
        issues=issues, best=best_per_spec(ds).to_dict("records"),
        value_specs=value_specs, value_rows=value_rows, heat=heat,
        data_json=json.dumps(data, ensure_ascii=False).replace("</", "<\\/"),
    )
    path.write_text(html, encoding="utf-8")
    return path


# --------------------------------------------------------------------------- Quarto / Markdown

def _md_table(df: pd.DataFrame) -> str:
    def esc(x) -> str:
        return str(x).replace("|", "\\|").replace("\n", " ")
    head = "| " + " | ".join(esc(c) for c in [df.index.name or ""] + list(df.columns)) + " |"
    def is_num(col) -> bool:
        vals = [str(v) for v in df[col] if str(v) not in ("", "nan")]
        return bool(vals) and all(re.fullmatch(r"[+\-]?[\d.,]+%?", v) for v in vals)
    sep = "|" + "|".join([":---"] + ["---:" if is_num(c) else ":---" for c in df.columns]) + "|"
    body = ["| " + " | ".join([esc(i)] + [esc(v) for v in row]) + " |" for i, row in zip(df.index, df.values)]
    return "\n".join([head, sep, *body])


def _chunks(items: list, size: int) -> list[list]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def write_markdown(ds: Dataset, comp: Comparison, issues: list[Issue], plots: dict, path: Path,
                   quarto: bool = True) -> Path:
    """report.qmd (render with `quarto render report.qmd --to html` or `--to pdf`) or plain report.md.
    Wide tables are split into groups of 6 specs so they fit on a page."""
    rel = lambda p: Path(p).relative_to(path.parent).as_posix()  # noqa: E731
    marked = lambda n: f"**{n}** (base)" if n == comp.base else n  # noqa: E731
    out: list[str] = []
    title = "Laptop comparison"
    if quarto:
        out += ["---", f'title: "{title}"', f'subtitle: "Base: {comp.base}"',
                f'date: "{datetime.now():%Y-%m-%d}"', "format:", "  html:", "    toc: true",
                "    embed-resources: true", "  pdf:", "    toc: true",
                "    geometry: [landscape, margin=1.5cm]", "    fontsize: 9pt", "---", ""]
    else:
        out += [f"# {title}", "", f"Base: **{comp.base}** · generated {datetime.now():%Y-%m-%d %H:%M}", ""]

    out += ["## Summary", ""]
    if issues:
        out.append(f"**{len(issues)} thing(s) to fix in the data:**\n")
        out += [f"- {i.message}  \n  → {i.fix}" for i in issues]
    else:
        out.append("Every spec has a type and every ranked value has a rank.")
    best = best_per_spec(ds)
    if not best.empty:
        out += ["", "### Best laptop for each spec", "", _md_table(best.set_index("Spec"))]

    out += ["", "## Comparison vs base", "",
            "% = difference vs the base. Price and weight: lower is better. "
            "Ranked specs without a score show better/worse by rank.", ""]
    text = comp.frame("text")
    text.index = [marked(n) for n in text.index]
    text.index.name = "Laptop"
    for group in _chunks(_display_specs(ds, comp), 6):
        out += [_md_table(text[group]), ""]

    out += ["## Spec values", ""]
    vals = ds.laptops.map(_value_text)
    vals.index = [marked(n) for n in vals.index]
    vals.index.name = "Laptop"
    for group in _chunks([c for c in _value_columns(ds) if c in vals.columns], 6):
        out += [_md_table(vals[group]), ""]

    if plots.get("overview"):
        out += ["## Overview", "", "Each spec scored 0–100 within this list (100 = best).", "",
                f"![Overview]({rel(plots['overview'])})", ""]
    out += ["## Per spec", "", "Every laptop sorted from low to high; the base is orange.", ""]
    for name, p in plots.get("specs", {}).items():
        out += [f"![{name}]({rel(p)})", ""]
    out += ["## Per laptop", ""]
    for n in comp.laptops:
        out += [f"### {n}{' (base)' if n == comp.base else ''}", ""]
        for k, v in _laptop_facts(ds, n):
            out.append(f"- **{k}:** {v}")
        if n in plots.get("laptops", {}):
            out += ["", f"![{n}]({rel(plots['laptops'][n])})"]
        out.append("")
    path.write_text("\n".join(out), encoding="utf-8")
    return path

