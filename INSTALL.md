# Installing laptop-compare with Anaconda (step by step)

You only do steps 1–3 once. After that, generating the report is step 4.

The project gets its **own conda environment** called `laptop-compare`. It is a separate, clean
Python with just what this project needs, so it can't break your other projects (or your base
Anaconda), and you can delete it any time.

## 1. Unzip the project
Put the `laptop-compare` folder somewhere simple, for example `C:\Users\<you>\Projects\laptop-compare`.

## 2. Open the Anaconda Prompt
Start menu → type **Anaconda Prompt** → open it. (Anaconda PowerShell Prompt works too.)
Then go to the project folder:

```
cd C:\Users\<you>\Projects\laptop-compare
```

Tip: in File Explorer you can copy the folder path from the address bar.

## 3. Create the environment (once, takes a few minutes)

```
conda env create -f environment.yml
```

This reads `environment.yml` and installs Python 3.12, pandas, matplotlib, jinja2 and pytest
from conda-forge, plus the project itself. When it finishes, check that it works:

```
conda activate laptop-compare
laptop-compare --version
```

You should see `laptop-compare 1.0.0`.

## 4. Generate the report (every time)

**The easy way:** double-click **`run_report.bat`** in the project folder. It activates the
environment, runs the comparison and opens `output\report.html` in your browser.

**From the Anaconda Prompt:**

```
conda activate laptop-compare
cd C:\Users\<you>\Projects\laptop-compare
laptop-compare
```

Useful options:

```
laptop-compare --base "zenbook"     REM default base for the CSVs and the Quarto report
laptop-compare --check              REM only check the data for problems
laptop-compare --list               REM show the laptop names
laptop-compare --csv-sep ";"        REM output CSVs that open directly in Excel/LibreOffice (Spain)
```

In the HTML report you can **change the base laptop with the dropdown at the top**: every
table and chart is redrawn. `--base` only sets which one is selected when the page opens (and
the base used in the CSVs and the Quarto report).

## 5. Edit the data
Open the CSVs in the `data` folder with LibreOffice/Excel or any text editor:

- `data\laptops.csv`: add a row per laptop
- `data\specs.csv`: how each column is compared
- `data\ranks\*.csv`: rank lists (add a CPU to `ranks\cpu.csv`)

When saving from LibreOffice/Excel choose **CSV, UTF-8**. Either `,` or `;` as separator works.
Then run step 4 again.

## Optional: PDF report with Quarto
Install Quarto from <https://quarto.org/docs/get-started/>, then:

```
quarto render output\report.qmd --to pdf
```

(The first time, Quarto may ask you to run `quarto install tinytex` for PDF support.)

## Optional: use it from WSL / Linux
Same steps in a terminal where conda is available. Use `./run_report.sh` instead of the `.bat`.

## Maintenance

| I want to… | Command (in Anaconda Prompt) |
|---|---|
| update the environment after `environment.yml` changes | `conda env update -f environment.yml --prune` |
| run the tests | `conda activate laptop-compare` then `pytest` |
| see my environments | `conda env list` |
| delete the environment | `conda env remove -n laptop-compare` |
| start over from scratch | remove it, then step 3 again |

## Troubleshooting

- **`'laptop-compare' is not recognized`**: the environment isn't active. Run `conda activate laptop-compare`.
- **`EnvironmentNameNotFound`**: step 3 wasn't done (or failed). Run it again from the project folder.
- **`environment.yml not found`**: you're not in the project folder. Use `cd` to go there first.
- **`run_report.bat` says it can't find Anaconda**: Anaconda is installed somewhere unusual. Use the Anaconda Prompt commands instead.
- **A ⚠ message about the data**: it says exactly which file and row to add (e.g. a CPU missing from `ranks\cpu.csv`).
