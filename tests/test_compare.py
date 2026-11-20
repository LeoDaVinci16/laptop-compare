"""Tests for the comparison rules and the data checks (run with: pytest)."""

import math
import shutil
from pathlib import Path

import pytest

from laptop_compare import compare, find_issues, goodness, load_dataset
from laptop_compare.compare import quantity
from laptop_compare.data import to_number

DATA = Path(__file__).resolve().parents[1] / "data"
BASE = "HP ProBook 4 G1i 14 (current)"


@pytest.fixture
def ds():
    return load_dataset(DATA)


@pytest.fixture
def tmp_data(tmp_path):
    """A copy of the data folder we can break on purpose."""
    dst = tmp_path / "data"
    shutil.copytree(DATA, dst)
    return dst


def test_bundled_data_is_clean(ds):
    assert find_issues(ds) == []


def test_higher_is_better_percent(ds):
    cell = compare(ds, BASE).cells[("LG gram 14 (14Z90T)", "RAM (GB)")]
    assert cell.text == "+100%" and cell.verdict == 1


def test_lower_is_better_flips_the_verdict(ds):
    comp = compare(ds, BASE)
    cheaper = comp.cells[("Acer Aspire 14 AI (A14-53M)", "Price (€)")]
    dearer = comp.cells[("Lenovo ThinkPad T14 Gen 7 (355)", "Price (€)")]
    assert cheaper.ratio < 0 and cheaper.verdict == 1
    assert dearer.ratio > 0 and dearer.verdict == -1


def test_ranked_with_score_gives_percent(ds):
    cell = compare(ds, BASE).cells[("LG gram 14 (14Z90T)", "CPU")]
    assert math.isclose(cell.ratio, 1006 / 527 - 1)


def test_ranked_without_score_gives_better_worse(ds):
    comp = compare(ds, BASE)
    assert comp.cells[("Asus Zenbook 14 OLED (UM3406KA)", "Panel")].text == "better (#1 vs #2)"
    assert comp.cells[("LG gram 14 (14Z90T)", "RAM upgradeable")].verdict == -1


def test_base_row_is_neutral(ds):
    comp = compare(ds, BASE)
    for spec in ds.columns("higher", "lower", "ranked"):
        v = comp.cells[(BASE, spec)].verdict
        assert math.isnan(v) or v == 0


def test_changing_the_base(ds):
    comp = compare(ds, "Lenovo ThinkPad T14 Gen 7 (355)")
    assert comp.cells[(BASE, "Price (€)")].verdict == 1   # the HP is cheaper than the T14


def test_cpu_sorted_low_to_high(ds):
    order = list(quantity(ds, "CPU").sort_values().index)
    assert order[0] == BASE and ds.laptops.at[order[-1], "CPU"] == "Intel Core Ultra 7 255H"


def test_goodness_range(ds):
    g = goodness(ds)
    assert g.min().min() >= 0 and g.max().max() <= 100
    assert g.at["Acer Aspire 14 AI (A14-53M)", "Price (€)"] == 100   # cheapest


def test_unranked_cpu_is_reported(tmp_data):
    with open(tmp_data / "laptops.csv", "a", encoding="utf-8") as f:
        f.write("New laptop,1500,Intel Core Ultra X7 358H,32,No,1000,70,1.3,14,No,IPS,1920×1200,120,500,2,1,Thunderbolt 4,Shop,\n")
    ds = load_dataset(tmp_data)
    messages = [i.message for i in find_issues(ds)]
    assert any("Intel Core Ultra X7 358H" in m and "not ranked" in m for m in messages)
    assert compare(ds, BASE).cells[("New laptop", "CPU")].status == "missing"


def test_column_without_type_is_reported(tmp_data):
    text = (tmp_data / "laptops.csv").read_text(encoding="utf-8").splitlines()
    text = [text[0] + ",Webcam"] + [line + ",1080p" for line in text[1:]]
    (tmp_data / "laptops.csv").write_text("\n".join(text) + "\n", encoding="utf-8")
    assert any("'Webcam'" in i.message and "no type" in i.message for i in find_issues(load_dataset(tmp_data)))


def test_missing_rank_file_is_reported(tmp_data):
    (tmp_data / "ranks" / "panel.csv").unlink()
    assert any("no rank file" in i.message for i in find_issues(load_dataset(tmp_data)))


@pytest.mark.parametrize("text,expected", [("1219", 1219), ("1219.5", 1219.5), ("1219,5", 1219.5),
                                           ("1.219,50", 1219.5), ("1 219 €", 1219), ("", math.nan)])
def test_to_number(text, expected):
    got = to_number(text)
    assert (math.isnan(got) and math.isnan(expected)) or got == expected


def test_html_report_has_every_base(ds, tmp_path):
    from laptop_compare.report import report_data, write_html

    data = report_data(ds, BASE)
    assert set(data["comp"]) == set(ds.names)              # one precomputed comparison per possible base
    assert data["comp"]["LG gram 14 (14Z90T)"][BASE]["CPU"][1] == -1   # vs the LG, the HP's CPU is worse
    html = write_html(ds, compare(ds, BASE), [], None, tmp_path / "r.html").read_text(encoding="utf-8")
    assert 'id="base"' in html and "const DATA" in html


def test_messy_csv_from_a_spreadsheet(tmp_path):
    """Extra empty columns, empty rows, ';' separator, Windows encoding: all must load."""
    from laptop_compare.data import read_csv

    p = tmp_path / "x.csv"
    p.write_bytes("Laptop;Price (€);CPU;\r\nA;1.219,50;X;;;\r\n;;;\r\nB;999;Y\r\n\r\n".encode("cp1252"))
    df = read_csv(p)
    assert list(df.columns) == ["Laptop", "Price (€)", "CPU"]
    assert df["Laptop"].tolist() == ["A", "B"]


def test_values_in_an_untitled_column_give_a_clear_error(tmp_path):
    from laptop_compare.data import DataFileError, read_csv

    p = tmp_path / "x.csv"
    p.write_text("Laptop,Price\nA,1,oops\n", encoding="utf-8")
    with pytest.raises(DataFileError, match="more values than there are column titles"):
        read_csv(p)
