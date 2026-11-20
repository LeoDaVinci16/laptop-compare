"""Load the CSV files that describe the laptops, the specs and the rank lists.

Folder layout expected by :func:`load_dataset`::

    data/
      laptops.csv        one row per laptop, one column per spec (first column = laptop name)
      specs.csv          one row per spec: spec, compare, rank_file, notes, formula (optional)
      ranks/<file>.csv   one file per "ranked" spec: value, rank, score, details
"""

from __future__ import annotations

import csv
import io
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

# The four ways a spec can be compared (column "compare" in specs.csv).
HIGHER = "higher"   # bigger number is better (RAM, battery...)
LOWER = "lower"     # smaller number is better (price, weight)
RANKED = "ranked"   # text values sorted in a rank file (CPU, panel...)
INFO = "info"       # shown, never compared (notes, shop...)
COMPARE_TYPES = (HIGHER, LOWER, RANKED, INFO)


@dataclass
class Spec:
    """One column of laptops.csv and how to compare it."""

    name: str
    compare: str
    rank_file: str = ""
    notes: str = ""
    formula: str = ""   # e.g. "ppi(Resolution, Screen (in))": calculated, not typed in laptops.csv

    @property
    def is_numeric(self) -> bool:
        return self.compare in (HIGHER, LOWER)

    @property
    def derived(self) -> bool:
        return bool(self.formula)


@dataclass
class RankTable:
    """The sorted list of known values for one ranked spec (e.g. every CPU)."""

    spec: str
    path: Path
    table: pd.DataFrame  # columns: value, rank, score, details (indexed by value)

    def has(self, value: str) -> bool:
        return value in self.table.index

    def rank(self, value: str) -> float:
        return float(self.table.at[value, "rank"])

    def score(self, value: str) -> float:
        """Optional numeric score (NaN when the rank file has no score for that value)."""
        return float(self.table.at[value, "score"])

    def details(self, value: str) -> str:
        return str(self.table.at[value, "details"]) if self.has(value) else ""


@dataclass
class Dataset:
    laptops: pd.DataFrame                       # index = laptop name, columns = specs (raw values)
    specs: dict[str, Spec]                      # spec name -> Spec, in specs.csv order
    ranks: dict[str, RankTable] = field(default_factory=dict)
    data_dir: Path = Path(".")
    raw: pd.DataFrame | None = None             # laptops.csv exactly as typed (text), for error messages
    name_column: str = "Laptop"                 # title of the first column of laptops.csv
    file_columns: list[str] = field(default_factory=list)  # columns really in laptops.csv (no calculated ones)

    @property
    def names(self) -> list[str]:
        return list(self.laptops.index)

    def columns(self, *types: str) -> list[str]:
        """Spec columns present in laptops.csv, in laptops.csv order, optionally filtered by type."""
        cols = [c for c in self.laptops.columns if c in self.specs]
        return [c for c in cols if not types or self.specs[c].compare in types]


# --------------------------------------------------------------------------- helpers

def slugify(text: str) -> str:
    """'Thunderbolt or USB4' -> 'thunderbolt_or_usb4' (used for default rank-file and plot names)."""
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "x"


def to_number(value) -> float:
    """Read numbers written in either style: 1219.50, 1.219,50, 1219,5, '1 219 €' -> float (NaN if empty)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return float("nan")
    if isinstance(value, (int, float)):
        return float(value)
    s = re.sub(r"[^\d,.\-]", "", str(value))
    if not s:
        return float("nan")
    if "," in s and "." in s:          # 1.219,50  -> thousands '.' and decimal ','
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:                     # 1219,5    -> decimal ','
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return float("nan")


class DataFileError(Exception):
    """A CSV file that can't be read, with a message that says what to fix."""


def _read_text(path: Path) -> str:
    """UTF-8 first (what we recommend); Excel's Windows encoding as a fallback (é, €, × still work)."""
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _detect_sep(header_line: str) -> str:
    """The header decides: whichever of ; , or tab appears most (outside quotes) is the separator."""
    unquoted = re.sub(r'"[^"]*"', "", header_line)
    counts = {sep: unquoted.count(sep) for sep in (",", ";", "\t")}
    return max(counts, key=counts.get) if max(counts.values()) else ","


def read_csv(path: Path) -> pd.DataFrame:
    """Read a CSV the forgiving way, because spreadsheet apps add surprises when they save:

    * ',' or ';' or tab as separator (LibreOffice/Excel in Spain often use ';')
    * UTF-8 or Windows encoding
    * extra empty columns at the end of some rows, and empty rows (ignored)
    * columns with no title (ignored, unless they contain data: then you get a clear error)
    """
    path = Path(path)
    text = _read_text(path)
    lines = text.splitlines()
    first = next((ln for ln in lines if ln.strip(" ,;\t")), "")
    if not first:
        raise DataFileError(f"{path.name} is empty.")
    rows = list(csv.reader(io.StringIO(text), delimiter=_detect_sep(first)))
    rows = [[c.strip() for c in r] for r in rows]
    rows = [r for r in rows if any(r)]                       # drop empty rows

    header = rows[0]
    while header and header[-1] == "":                       # drop untitled columns at the end
        header = header[:-1]
    width = len(header)
    data = []
    for line_no, r in enumerate(rows[1:], start=2):
        extra = [c for c in r[width:] if c]
        if extra:
            raise DataFileError(
                f"{path.name}, row starting '{r[0][:40]}': it has more values than there are column titles "
                f"(extra: {', '.join(extra[:3])}). Add a title for that column or remove the extra values.")
        data.append((r + [""] * width)[:width])
    keep = [i for i, h in enumerate(header) if h or any(row[i] for row in data)]
    if any(not header[i] for i in keep):
        raise DataFileError(f"{path.name} has a column with values but no title. Give it a title in the first row.")
    return pd.DataFrame([[row[i] for i in keep] for row in data], columns=[header[i] for i in keep], dtype=str)


# --------------------------------------------------------------------------- calculated specs

def _ppi(resolution, screen) -> float:
    """Pixels per inch from '1920×1200' (any separator) and the diagonal in inches."""
    nums = re.findall(r"\d+", str(resolution or ""))
    diag = to_number(screen)
    if len(nums) < 2 or not diag or math.isnan(diag):
        return float("nan")
    w, h = int(nums[0]), int(nums[1])
    return round(math.hypot(w, h) / diag, 0)


# name -> (function, number of inputs). Add new calculated specs here.
FORMULAS = {"ppi": (_ppi, 2)}


class FormulaError(ValueError):
    pass


def parse_formula(text: str) -> tuple[str, list[str]]:
    """'ppi(Resolution, Screen (in))' -> ('ppi', ['Resolution', 'Screen (in)'])"""
    m = re.fullmatch(r"\s*(\w+)\s*\((.*)\)\s*", text or "")
    if not m:
        raise FormulaError(f"'{text}' is not written like name(column, column).")
    name, args = m.group(1).lower(), [a.strip() for a in m.group(2).split(",") if a.strip()]
    if name not in FORMULAS:
        raise FormulaError(f"unknown formula '{name}' (known: {', '.join(FORMULAS)}).")
    if len(args) != FORMULAS[name][1]:
        raise FormulaError(f"{name} needs {FORMULAS[name][1]} columns, got {len(args)}.")
    return name, args


def _add_derived(laptops: pd.DataFrame, raw: pd.DataFrame, specs: dict[str, Spec]) -> None:
    """Calculate every spec that has a formula and insert it right after the last column it uses."""
    for spec in specs.values():
        if not spec.derived:
            continue
        try:
            name, args = parse_formula(spec.formula)
        except FormulaError:
            continue                                   # reported by validate.find_issues
        if any(a not in raw.columns for a in args) or spec.name in raw.columns:
            continue
        fn = FORMULAS[name][0]
        values = [fn(*(raw.at[n, a] for a in args)) for n in raw.index]
        pos = max(list(raw.columns).index(a) for a in args) + 1
        laptops.insert(pos, spec.name, values)
        raw.insert(pos, spec.name, ["" if math.isnan(v) else f"{v:g}" for v in values])


# --------------------------------------------------------------------------- loading

def load_specs(path: Path) -> dict[str, Spec]:
    df = read_csv(path)
    specs: dict[str, Spec] = {}
    for _, row in df.iterrows():
        name = row.get("spec", "")
        if not name:
            continue
        specs[name] = Spec(
            name=name,
            compare=row.get("compare", "").lower(),
            rank_file=row.get("rank_file", ""),
            notes=row.get("notes", ""),
            formula=row.get("formula", ""),
        )
    return specs


def load_rank_table(spec: Spec, ranks_dir: Path) -> RankTable | None:
    path = ranks_dir / (spec.rank_file or f"{slugify(spec.name)}.csv")
    if not path.exists():
        return None
    df = read_csv(path)
    for col in ("value", "rank", "score", "details"):
        if col not in df.columns:
            df[col] = ""
    df = df[df["value"] != ""].copy()
    df["rank"] = df["rank"].map(to_number)
    df["score"] = df["score"].map(to_number)
    df = df.drop_duplicates("value", keep="first").set_index("value")
    return RankTable(spec=spec.name, path=path, table=df[["rank", "score", "details"]])


def load_dataset(data_dir: str | Path) -> Dataset:
    data_dir = Path(data_dir)
    laptops = read_csv(data_dir / "laptops.csv")
    name_col = laptops.columns[0]
    laptops = laptops[laptops[name_col] != ""].set_index(name_col)
    laptops.index.name = "Laptop"
    raw = laptops.copy()

    specs = load_specs(data_dir / "specs.csv")
    file_columns = list(laptops.columns)

    # numbers become floats, everything else stays text
    for col in laptops.columns:
        if col in specs and specs[col].is_numeric:
            laptops[col] = laptops[col].map(to_number)
    _add_derived(laptops, raw, specs)

    ranks = {}
    for spec in specs.values():
        if spec.compare == RANKED:
            table = load_rank_table(spec, data_dir / "ranks")
            if table is not None:
                ranks[spec.name] = table

    return Dataset(laptops=laptops, specs=specs, ranks=ranks, data_dir=data_dir, raw=raw, name_column=name_col,
                   file_columns=file_columns)


# --------------------------------------------------------------------------- selection (which laptops / specs to use)

SELECTION_FILE = "selection.json"


def load_selection(data_dir: str | Path) -> dict:
    """data/selection.json lists what is switched OFF, so new laptops and specs are on by default:
    {"laptops_off": ["..."], "specs_off": ["Resolution"]}. Missing file = everything on."""
    path = Path(data_dir) / SELECTION_FILE
    sel = {"laptops_off": [], "specs_off": []}
    if path.exists():
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
            for key in sel:
                sel[key] = [str(x) for x in saved.get(key, [])]
        except (json.JSONDecodeError, AttributeError):
            pass  # a broken file is treated as "everything on"
    return sel


def save_selection(data_dir: str | Path, sel: dict) -> Path:
    path = Path(data_dir) / SELECTION_FILE
    clean = {k: sorted(set(map(str, sel.get(k, [])))) for k in ("laptops_off", "specs_off")}
    path.write_text(json.dumps(clean, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def apply_selection(ds: Dataset, sel: dict) -> Dataset:
    """A copy of the dataset without the laptops and specs that are switched off."""
    rows = [n for n in ds.names if n not in set(sel.get("laptops_off", []))]
    if not rows:            # never end up with nothing to compare
        rows = ds.names
    cols = [c for c in ds.laptops.columns if c not in set(sel.get("specs_off", []))]
    raw = ds.raw.loc[rows, cols] if ds.raw is not None else None
    specs = {k: v for k, v in ds.specs.items() if k not in set(sel.get("specs_off", []))}
    return Dataset(laptops=ds.laptops.loc[rows, cols], specs=specs, ranks=ds.ranks,
                   data_dir=ds.data_dir, raw=raw, name_column=ds.name_column,
                   file_columns=[c for c in ds.file_columns if c in cols])
