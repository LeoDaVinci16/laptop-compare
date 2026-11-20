"""Add a laptop (and new rank values, e.g. a new CPU) to the CSV files.

Rows are *appended* to the end of the existing files, keeping their separator and encoding,
so whatever formatting your spreadsheet app saved is left untouched.
"""

from __future__ import annotations

import csv
import io
import math
from pathlib import Path

from .data import RANKED, _detect_sep, load_dataset, slugify, to_number


class AddLaptopError(ValueError):
    """The laptop can't be added; the message says why."""


def _file_format(path: Path) -> tuple[str, str]:
    """(encoding, separator) of an existing CSV, so appended rows match it."""
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
        enc = "utf-8"
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")
        enc = "cp1252"
    first = next((ln for ln in text.splitlines() if ln.strip(" ,;\t")), "")
    return enc, _detect_sep(first)


def _append_row(path: Path, values: list[str], header: list[str] | None = None) -> None:
    """Append one CSV row (creating the file with `header` if it doesn't exist)."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        enc, sep = "utf-8", ","
        buf = io.StringIO()
        csv.writer(buf, delimiter=sep, lineterminator="\n").writerow(header or [])
        path.write_text(buf.getvalue(), encoding=enc)
    enc, sep = _file_format(path)
    existing = path.read_bytes()
    buf = io.StringIO()
    csv.writer(buf, delimiter=sep, lineterminator="\r\n" if b"\r\n" in existing else "\n").writerow(values)
    with open(path, "a", encoding=enc, newline="") as f:
        if existing and not existing.endswith((b"\n", b"\r")):
            f.write("\r\n" if b"\r\n" in existing else "\n")
        f.write(buf.getvalue())


def _clean_number(text: str) -> str:
    """'1.219,50' -> '1219.5'  ('' stays ''). Raises if it isn't a number."""
    if not text.strip():
        return ""
    n = to_number(text)
    if math.isnan(n):
        raise ValueError(text)
    return f"{n:g}" if abs(n) < 1e15 else str(n)


def add_laptop(data_dir: str | Path, values: dict[str, str], new_ranks: dict[str, dict] | None = None) -> list[str]:
    """Append a laptop to laptops.csv.

    values     {column title: value}; the laptop name goes under the first column's title.
    new_ranks  {spec: {"rank": "3", "score": "700", "details": "..."}} for ranked values that are not
               in their rank file yet (e.g. a new CPU). They are appended to ranks/<file>.csv.

    Returns a list of messages (what was done, plus anything still to fix).
    """
    data_dir = Path(data_dir)
    new_ranks = new_ranks or {}
    ds = load_dataset(data_dir)
    values = {k: str(v).strip() for k, v in values.items() if v is not None}

    name = values.get(ds.name_column, "")
    if not name:
        raise AddLaptopError("The laptop needs a name.")
    if name in ds.names:
        raise AddLaptopError(f"There is already a laptop called '{name}'. Use a different name (add the model code).")

    row = [name]
    errors = []
    for col in ds.laptops.columns:
        v = values.get(col, "")
        spec = ds.specs.get(col)
        if spec is not None and spec.is_numeric:
            try:
                v = _clean_number(v)
            except ValueError:
                errors.append(f"{col}: '{v}' is not a number")
        row.append(v)
    if errors:
        raise AddLaptopError("Please fix: " + "; ".join(errors))

    # new rank values first, so the laptop is complete as soon as it is added
    messages = []
    for spec_name, info in new_ranks.items():
        spec = ds.specs.get(spec_name)
        value = values.get(spec_name, "")
        rank_text = str(info.get("rank", "")).strip()
        if not value or not rank_text or spec is None or spec.compare != RANKED:
            continue
        table = ds.ranks.get(spec_name)
        if table is not None and table.has(value):
            continue
        try:
            rank = _clean_number(rank_text)
            score = _clean_number(str(info.get("score", "")))
        except ValueError:
            raise AddLaptopError(f"{spec_name}: rank and score must be numbers.") from None
        path = table.path if table is not None else data_dir / "ranks" / (spec.rank_file or f"{slugify(spec_name)}.csv")
        _append_row(path, [value, rank, score, str(info.get("details", "")).strip()],
                    header=["value", "rank", "score", "details"])
        messages.append(f"Added {spec_name} '{value}' to ranks/{path.name} with rank {rank}"
                        + (f" and score {score}" if score else "") + ".")

    _append_row(data_dir / "laptops.csv", row)
    messages.insert(0, f"Added '{name}' to laptops.csv.")

    # anything still missing?
    from .validate import find_issues

    ds2 = load_dataset(data_dir)
    for issue in find_issues(ds2):
        if f"used by {name}" in issue.message or name in issue.message:
            messages.append(f"Still to do: {issue.message} → {issue.fix}")
    return messages
