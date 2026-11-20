# laptop-compare

Compare laptops spec by spec against a **base laptop** (the one you have now, or any other).
It works like the spreadsheet, but from CSV files:

- `output/comparison.csv`: the comparison table (`+70%`, `better (#1 vs #2)`, …)
- `output/report.html`: one self-contained, interactive report: pick the base laptop in the page
- `output/report.qmd`: the same report for Quarto (`quarto render report.qmd --to pdf`)
- `output/plots/*.png`: the same charts as images (used by the Quarto report)

## Install (Anaconda)

Full beginner steps are in **[INSTALL.md](INSTALL.md)**. In short, from the Anaconda Prompt inside this folder:

```
conda env create -f environment.yml      # once
conda activate laptop-compare
laptop-compare                           # writes output/ (or double-click run_report.bat)
```

## Run

```bash
laptop-compare                                   # base = first laptop in laptops.csv
laptop-compare --base "zenbook"                  # part of the name is enough if it's unique
laptop-compare --list                            # show the laptop names
laptop-compare --check                           # only check the data (alerts), write nothing
laptop-compare --format html qmd md              # choose report formats (default: html qmd)
laptop-compare --csv-sep ";"                     # CSVs that Excel/LibreOffice in Spain open directly
laptop-compare --data other_folder --out results
```

### App mode (add laptops, choose laptops and specs)

```
laptop-compare --serve          # or double-click run_app.bat
```

Opens the report in your browser from a small local web server (Python's built-in one,
listening only on this computer). The page has four tabs:

| Tab | What it does |
|---|---|
| **Home** | entrance page: base laptop, key numbers, highlights, then summary, comparison, values and overview |
| **Per spec** | one chart per spec, selected laptops sorted low → high |
| **Per laptop** | each laptop vs the base (advantage bars + radar), with a "jump to" menu |
| **Laptops** | tick/untick laptops to keep charts readable or narrow down to finalists; **✎ Edit** opens a laptop in the form to correct it |
| **Specs** | tick/untick the specs that matter to you (e.g. drop Resolution); scores and "best" update too |
| **Add laptop** | a form with one box per spec; new CPUs/ranked values can be ranked right there (also used for editing) |

Editing replaces only that laptop's row in `laptops.csv` (renaming works; the saved selection follows the new name).

**Save as default** writes the ticks to `data/selection.json` (it lists what is switched *off*,
so new laptops and specs appear switched on). The CSVs and the Quarto report also use it;
`--all` ignores it. Rows are appended to the CSVs, keeping their separator and encoding.

The static `output/report.html` has the same tabs: ticking works there too, but adding
laptops and saving need app mode.

### Changing the base laptop
- **In the HTML report:** use the **Base laptop** dropdown at the top. The comparison table,
  every chart and every laptop card are redrawn instantly; no Python needed. The choice is
  kept in the address (`report.html#base=...`), so you can bookmark it.
- **On the command line:** `--base` chooses the base for the CSVs and the Quarto/Markdown
  report, and which laptop the HTML opens with.

## The data (folder `data/`)

The files can use `,` or `;` as separator and `1219.5` or `1219,5` for decimals. Save them as UTF-8.

### `laptops.csv`: one row per laptop
The first column is the laptop name, and every other column is a spec. **To add a laptop, add a row.**
To add a spec, add a column, then describe it in `specs.csv`.

### `specs.csv`: how each column is compared
| spec | compare | rank_file | notes |
|---|---|---|---|
| Price (€) | lower | | |
| CPU | ranked | cpu.csv | Score = Cinebench 2024 multi-core |
| RAM (GB) | higher | | |
| Notes | info | | |

`compare` is one of:
- `higher`: a bigger number is better (RAM, battery, ports)
- `lower`: a smaller number is better (price, weight)
- `ranked`: text values sorted in a rank file (CPU, panel, Thunderbolt…)
- `info`: shown but not compared (notes, shop, screen size)

### `ranks/<file>.csv`: one file per ranked spec
```csv
value,rank,score,details
Intel Core Ultra 7 255H,1,1006,"Single-core 124 · ..."
AMD Ryzen AI 7 350,2,895,...
```
- `value`: exactly as written in `laptops.csv`
- `rank`: 1 = best (equal ranks are fine)
- `score`: optional. If both laptops' values have a score, the comparison is a % (CPU: "+70%");
  otherwise it is `better/same/worse (#rank vs #rank)`.
- `details`: free text, shown in each laptop's section of the report

**Adding a new CPU:** add one row to `ranks/cpu.csv` with its name, rank and (optionally) score.

## Alerts
Every run checks the data and tells you exactly what to add. For example:

```
⚠ CPU 'Intel Core Ultra X7 358H' is not ranked (used by New laptop).
    → Add a row to ranks/cpu.csv: Intel Core Ultra X7 358H,<rank>,<score (optional)>,<details>
```

It also catches a column with no row in `specs.csv`, a ranked spec without a rank file, numbers
that aren't numbers, and duplicated laptop names. In the report, cells that are affected turn orange.
`--strict` stops the run when there are errors, and `--check` returns exit code 1 (useful in scripts).

## How the comparison works
| spec type | cell shows | green when |
|---|---|---|
| higher | % vs base | the laptop has more |
| lower | % vs base | the laptop has less (cheaper, lighter) |
| ranked + score | % of the scores | higher score |
| ranked | better / same / worse (#rank vs #rank) | better rank |
| info | the value | not compared |

The charts and the heatmap use a **0–100 score per spec** within the list (100 = best laptop
for that spec, 0 = worst). Ranked specs without scores are scored by rank.

### Charts
- **Per spec** (`plots/spec_*.png`): every laptop sorted low → high (price from cheap to expensive
  as a line plot, CPU from low tier to high as bars, ranked specs as tiers). The base is orange.
- **Per laptop** (`plots/laptop_*.png`): on the left, how much better or worse it is than the base
  for each spec; on the right, a radar chart of its 0–100 scores against the base.
- **Overview** (`plots/overview_heatmap.png`): every laptop × every spec.

## Output CSVs
| file | content |
|---|---|
| `comparison.csv` | the table as you read it (`+70%`, `better (#1 vs #2)`) |
| `comparison_ratios.csv` | % differences as numbers (0.7 = +70%) |
| `comparison_verdicts.csv` | +1 better / 0 same / −1 worse (already accounts for lower-is-better) |
| `scores_0_100.csv` | the heatmap values |

## Project layout
```
src/laptop_compare/
  data.py        load the CSVs (separator and decimal detection, number parsing)
  validate.py    alerts: missing types, unranked values, missing rank files...
  compare.py     comparison rules, sorting (low → high), 0–100 scores, best per spec
  plots.py       charts (matplotlib)
  report.py      CSVs, interactive HTML report (template + charts in templates/report.html.j2),
                 Quarto/Markdown report
  editing.py     add a laptop / new rank values to the CSVs
  server.py      app mode (local web server, standard library only)
  cli.py         command line
tests/           pytest tests for the rules and the alerts
```

## Tests
```bash
conda activate laptop-compare
pytest
```
