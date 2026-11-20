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


# ---------------------------------------------------------------- selection and adding laptops

def test_selection_switches_laptops_and_specs_off(tmp_data):
    from laptop_compare.data import apply_selection, load_selection, save_selection

    save_selection(tmp_data, {"laptops_off": ["Mac?", "LG gram 14 (14Z90T)"], "specs_off": ["Resolution"]})
    ds = load_dataset(tmp_data)
    sub = apply_selection(ds, load_selection(tmp_data))
    assert "LG gram 14 (14Z90T)" not in sub.names and "Resolution" not in sub.laptops.columns
    assert find_issues(sub) == []          # a switched-off spec must not raise "not a column" warnings


def test_add_laptop_with_a_new_cpu(tmp_data):
    from laptop_compare.editing import add_laptop

    msgs = add_laptop(tmp_data, {"Laptop": "Test 14", "Price (€)": "1.399,50", "CPU": "Intel Core Ultra X7 358H",
                                 "Weight (kg)": "1,3", "Notes": "has, a comma"},
                      {"CPU": {"rank": "1", "score": "1100", "details": "estimate"}})
    assert any("Added 'Test 14'" in m for m in msgs)
    ds = load_dataset(tmp_data)
    assert ds.laptops.at["Test 14", "Price (€)"] == 1399.5 and ds.laptops.at["Test 14", "Notes"] == "has, a comma"
    assert ds.ranks["CPU"].score("Intel Core Ultra X7 358H") == 1100
    assert find_issues(ds) == []


def test_add_laptop_refuses_duplicates_and_bad_numbers(tmp_data):
    from laptop_compare.editing import AddLaptopError, add_laptop

    with pytest.raises(AddLaptopError, match="already"):
        add_laptop(tmp_data, {"Laptop": BASE})
    with pytest.raises(AddLaptopError, match="not a number"):
        add_laptop(tmp_data, {"Laptop": "X", "Price (€)": "cheap"})
    with pytest.raises(AddLaptopError, match="needs a name"):
        add_laptop(tmp_data, {"Price (€)": "1000"})


def test_unranked_value_without_rank_is_reported_after_adding(tmp_data):
    from laptop_compare.editing import add_laptop

    msgs = add_laptop(tmp_data, {"Laptop": "Y", "CPU": "Apple M4"})
    assert any("Still to do" in m and "Apple M4" in m for m in msgs)


def test_edit_laptop_replaces_only_its_row(tmp_data):
    from laptop_compare.data import load_selection, save_selection
    from laptop_compare.editing import update_laptop

    save_selection(tmp_data, {"laptops_off": ["LG gram 14 (14Z90T)"], "specs_off": []})
    before = load_dataset(tmp_data)
    values = {c: before.raw.at["LG gram 14 (14Z90T)", c] for c in before.laptops.columns}
    values.update({"Laptop": "LG gram 14 2025", "Price (€)": "1.199,00"})
    msgs = update_laptop(tmp_data, "LG gram 14 (14Z90T)", values)
    assert any("Renamed" in m for m in msgs)
    after = load_dataset(tmp_data)
    assert after.names.index("LG gram 14 2025") == before.names.index("LG gram 14 (14Z90T)")   # same position
    assert after.laptops.at["LG gram 14 2025", "Price (€)"] == 1199
    assert len(after.names) == len(before.names)
    assert load_selection(tmp_data)["laptops_off"] == ["LG gram 14 2025"]                      # selection follows the rename
    other = "Acer Aspire 14 AI (A14-53M)"
    assert after.raw.loc[other].tolist() == before.raw.loc[other].tolist()                    # other rows untouched


def test_edit_refuses_taking_another_laptops_name(tmp_data):
    from laptop_compare.editing import AddLaptopError, update_laptop

    with pytest.raises(AddLaptopError, match="already"):
        update_laptop(tmp_data, "LG gram 14 (14Z90T)", {"Laptop": BASE})


def test_save_by_name_replaces_or_adds(tmp_data):
    from laptop_compare.editing import save_laptop

    before = load_dataset(tmp_data)
    msi = "MSI Prestige 14 AI Evo (C2HMG)"
    values = {c: before.raw.at[msi, c] for c in before.laptops.columns} | {"Laptop": msi, "Price (€)": "1199"}
    assert "Updated" in save_laptop(tmp_data, values)[0]                 # same name -> replaced
    after = load_dataset(tmp_data)
    assert len(after.names) == len(before.names) and after.laptops.at[msi, "Price (€)"] == 1199
    assert "Added" in save_laptop(tmp_data, values | {"Laptop": "MSI copy"})[0]   # new name -> added
    assert len(load_dataset(tmp_data).names) == len(before.names) + 1


def _add_ppi_spec(data_dir: Path, formula: str = "ppi(Resolution, Screen (in))") -> None:
    path = data_dir / "specs.csv"
    lines = path.read_text(encoding="utf-8").rstrip("\n").split("\n")
    if "formula" not in lines[0]:
        lines[0] += ",formula"
    lines.append(f'Pixel density (ppi),higher,,,"{formula}"')
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_calculated_spec_is_added_after_its_inputs(tmp_data):
    _add_ppi_spec(tmp_data)
    ds = load_dataset(tmp_data)
    cols = list(ds.laptops.columns)
    assert cols.index("Pixel density (ppi)") == max(cols.index("Resolution"), cols.index("Screen (in)")) + 1
    assert "Pixel density (ppi)" not in ds.file_columns
    name = ds.names[0]
    if ds.raw.at[name, "Resolution"] == "1920×1200" and ds.raw.at[name, "Screen (in)"] == "14":
        assert ds.laptops.at[name, "Pixel density (ppi)"] == 162
    assert not [i for i in find_issues(ds) if "ppi" in i.message]


def test_calculated_spec_is_never_written_to_the_csv(tmp_data):
    from laptop_compare.editing import save_laptop

    _add_ppi_spec(tmp_data)
    ds = load_dataset(tmp_data)
    name = ds.names[0]
    values = {ds.name_column: name, **{c: ds.raw.at[name, c] for c in ds.file_columns}}
    values["Pixel density (ppi)"] = "999"
    header_before = (tmp_data / "laptops.csv").read_text(encoding="utf-8").splitlines()[0]
    save_laptop(tmp_data, values)
    assert (tmp_data / "laptops.csv").read_text(encoding="utf-8").splitlines()[0] == header_before
    assert load_dataset(tmp_data).laptops.at[name, "Pixel density (ppi)"] != 999


def test_bad_formula_is_reported(tmp_data):
    _add_ppi_spec(tmp_data, "ppi(Resolution, Nope)")
    msgs = [i.message for i in find_issues(load_dataset(tmp_data))]
    assert any("'Nope'" in m for m in msgs)
