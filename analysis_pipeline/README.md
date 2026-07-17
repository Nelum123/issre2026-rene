# Better Distributional Fit Does Not Improve Reachable Coverage Estimation in Fuzzing

This README explains how to set up and run `analysis.ipynb`.


1. Discovers and loads campaign artifacts (per-run coverage data).
2. Builds subject-level artifacts (incidence / hit-count matrices across runs).
3. Fits parametric models to the observed incidence-frequency data.
4. Computes richness estimators (Chao2, Chao2_bc, Jackknife1, Chiu, Lanumteang-Böhning,
   Gamma-Poisson, Zipf-Mandelbrot) from the fitted parameters.
5. Compares parametric and non-parametric estimators against known ground-truth totals
6. Saves summary tables, plot data, and the paper tables/figures.

## Requirements

- Python 3.10+
- `numpy`, `pandas`, `scipy`, `matplotlib`, `seaborn`, `jupyter`

```bash
pip install numpy pandas scipy matplotlib seaborn jupyter
```

## Expected input data layout

Set `RAW_DATA_DIR` (cell 2) to the folder containing your fuzzing campaign data. Each
campaign run must be a subfolder named:

```
<subject>_aflpp_run_<n>/coverage/ft_cov_*.json
```

e.g. `parsera_aflpp_run_1/coverage/ft_cov_00001.json`. Each coverage JSON must contain a
`block_coverage` array (the key name is set by `COVERAGE_KEY` in cell 2). `<subject>` is
whatever you named the target (e.g. `parsera`, `libxml2`, `freetype2`) — it is *not*
determined by any config, it's just parsed out of the folder name via `RUN_DIR_RE`.

## Key configuration (cell 2)

```python
RAW_DATA_DIR = Path("/Data")              # <- point this at your raw campaign data
OUTPUT_DIR = Path("./analysis_outputs")   # where all generated artifacts/tables go
REBUILD_CAMPAIGN_ARTIFACTS = False        # True the first time you add/change raw data
REBUILD_SUBJECT_ARTIFACTS = False         # True the first time you add/change raw data

KNOWN_TOTALS = {
    "parsera": 104952,
    "parserb": 136455,
    "parserc": 231510,
    "parserd": 331301,
    "parsere": 289070,
}
```

`KNOWN_TOTALS` is the master switch that decides which subjects are treated as
**synthetic parsers with a known ground truth** (ground truth total block count on the
right) versus **real-world programs** (anything discovered that is *not* a key in this
dict). Any subject not listed here is automatically classified as `real_world` with
`known_total = NaN` — bias and relative error are intentionally left blank for those,
since there's no ground truth to compare against.

When `REBUILD_* = False`, the notebook loads previously-built indices from
`analysis_outputs/campaign_artifact_index.csv` and `analysis_outputs/subject_artifact_index.csv`
instead of rebuilding from raw data — these must already exist for that path to work.

## Running for parser (synthetic) programs  and real-world programs

This is what the notebook does out of the box:

1. Set `RAW_DATA_DIR` to your data folder (cell 2).
2. First run only: set `REBUILD_CAMPAIGN_ARTIFACTS = True` and
   `REBUILD_SUBJECT_ARTIFACTS = True` so the `.pkl` artifacts and index CSVs get built.
   On later runs you can leave both `False` to skip rebuilding.
3. Confirm `KNOWN_TOTALS` (cell 2) lists your parser subjects with the correct true
   totals.
4. Run the notebook top to bottom (`Kernel > Restart & Run All`).

This alone populates every table that depends on `KNOWN_TOTALS` subjects: the model-fit
tables, `paper_table_estimator_performance.csv` (bias/relative error), the per-subject
estimator comparison tables, and the synthetic Zipf-Mandelbrot rank-frequency plots.



## Outputs

Everything lands under `analysis_outputs/`:

```
analysis_outputs/
  campaign_artifact_index.csv
  subject_artifact_index.csv
  campaign_artifacts/<campaign_name>/          # incidence.pkl, hit_counts.pkl, metadata.json
  subject_artifacts/<subject>/                 # incidence.pkl, final_hit_count.pkl, metadata.json
  summaries/
    subject_parametric_fit_summary*.csv
    estimator_comparison_*.csv
    estimator_summary_*.csv / estimator_relative_behavior_*.csv
    plot_data/                                 # per-figure raw/summary CSVs
      zipf_rank_frequency_ascending/            # synthetic parsers
      zipf_rank_frequency_ascending_real_world/  # real-world programs
    plots/                                      # per-subject fit-curve CSVs
    paper_tables/                               # final tables used in the paper
```


