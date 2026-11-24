# Cross-Solver Anti-Bandwidth Benchmark Comparison: Kissat 4.0.4 vs CaDiCaL 3.0.0 vs CaDiCaL 1.2.1

This document describes the cross-solver benchmarking methodology, metrics, and automated tooling used to evaluate the **Anti-Bandwidth Problem (ABP)** Sequential Counter Ladder (SCL) formulation across three distinct SAT solver configurations:

1. **Kissat 4.0.4 (`kissat404`)**: In-process Python solver via **PySAT** with isolated fork-based worker execution.
2. **CaDiCaL 3.0.0 (`cadical300`)**: Modern CaDiCaL solver via **PySAT** with identical isolated fork-based worker execution.
3. **CaDiCaL 1.2.1 (`cadical121`)**: Legacy native C++ reference implementation from [AntiBandwidthSCL](https://github.com/TruongXuanHieu-H/AntiBandwidthSCL.git).

For details on problem formulation and SCL ladder encoding mathematics, refer to [docs/encoding.md](encoding.md). For details on symmetry breaking modes (`n`, `f`, `h`, `l`), refer to [README.md#symmetry-breaking-modes](../README.md#symmetry-breaking-modes).

---

## 1. Benchmarking Setup & Metric Parity

All solvers evaluate the standard 24 Matrix Market benchmark graph instances from Markus Sinnl (2018) under identical experimental constraints:

- **Hardware Platform**: Linux x86_64 single-threaded execution.
- **Resource Constraints**:
  - Wall-clock time limit: **1,800.0 seconds** (30 minutes) per graph instance.
  - Memory limit: **30.0 GB** per decision step.
- **Search Strategy**: Incremental linear search from published lower bound $LB$ upward towards upper bound $UB$, terminating upon the first `UNSAT` decision or early exit at $UB$.

### 1.1 Metric Parity Across Solver Backends

To ensure an unbiased side-by-side comparison between the Python PySAT backends and the compiled C++ binary:

| Dimension | Kissat 4.0.4 (PySAT) | CaDiCaL 3.0.0 (PySAT) | CaDiCaL 1.2.1 (Native C++) |
| :--- | :--- | :--- | :--- |
| **Execution Wrapping** | In-process Python worker with `resource.RLIMIT_AS` | In-process Python worker with `resource.RLIMIT_AS` | External process managed via `runlim` (`--time=1800 --real=1800 --space=30000`) |
| **`total_time_s`** | Cumulative wall-clock search time (`time.perf_counter()`) | Cumulative wall-clock search time (`time.perf_counter()`) | Cumulative wall-clock search time (`[runlim] real: <sec>`) |
| **Optimal Bandwidth $w^*$** | Highest feasible bandwidth proved SAT before timeout / UNSAT | Highest feasible bandwidth proved SAT before timeout / UNSAT | Highest feasible bandwidth proved SAT before timeout / UNSAT |
| **Search Status** | `OPTIMAL`, `TIMEOUT`, `MEMOUT`, `UNSAT_START`, `ERROR` | `OPTIMAL`, `TIMEOUT`, `MEMOUT`, `UNSAT_START`, `ERROR` | `OPTIMAL`, `TIMEOUT`, `MEMOUT`, `UNSAT`, `ERROR` |
| **Certificate Verification** | Independent certificate verification via `SolutionVerifier` | Independent certificate verification via `SolutionVerifier` | Internal assignment validation |

### 1.2 Standard 11-Column CSV Schema

All solvers produce (or are parsed into) a standardized 11-column `summary.csv`:

```text
instance,n,m,lower_bound,upper_bound,optimal_w,status,total_time_s,steps_evaluated,sym_mode,verified
```

1. `instance`: Graph filename (e.g. `A-pores_1.mtx.rnd`).
2. `n`: Vertex count $|V|$.
3. `m`: Edge count $|E|$. When CaDiCaL `.out` logs omit original header files, $m$ is derived analytically via $m = C_{\text{glue}} // e(n, w)$.
4. `lower_bound`: Benchmark reference lower bound.
5. `upper_bound`: Benchmark reference upper bound.
6. `optimal_w`: Maximum feasible anti-bandwidth found (empty string if no SAT step completed).
7. `status`: Outcome (`OPTIMAL`, `TIMEOUT`, `MEMOUT`, `UNSAT`, `UNSAT_START`, `ERROR`).
8. `total_time_s`: Wall-clock execution time formatted to 3 decimal places.
9. `steps_evaluated`: Total number of decision steps solved.
10. `sym_mode`: Symmetry breaking mode code (`f`, `h`, `n`, `l`).
11. `verified`: Solution certificate validation boolean (`True`/`False`).

---

## 2. Solver Comparison & Evaluation Criteria

When comparing solvers on an instance within a symmetry breaking mode:

1. **Zero-Solution Rule**:
   If no solver discovers a feasible labeling (i.e. all solvers have `optimal_w is None`), no solver is crowned a winner and no cells are bolded.
2. **Bandwidth Superiority ($w^*$)**:
   The solver that discovers a strictly higher feasible bandwidth $w^*$ is the superior solver for that instance.
3. **Status Superiority**:
   If multiple solvers achieve the same $w^*$, proving `OPTIMAL` (by proving $w^* + 1$ is `UNSAT` or early exiting at $UB$) beats `TIMEOUT` or `MEMOUT`.
4. **Runtime Tie-Breaker**:
   If multiple solvers prove `OPTIMAL` with identical $w^*$, the solver with the faster wall-clock runtime (`total_time_s`) is superior (threshold: $\Delta t > 0.005\text{ s}$).
5. **Multi-Winner Tie Rule**:
   If multiple solvers tie for first place (e.g. both are `OPTIMAL` with runtimes within $0.005\text{ s}$, or both tie at the highest $w^*$ with `TIMEOUT` status), all tying winners have their three result cells (`optimal_w`, `time`, `status`) bolded.

---

## 3. Comparison Tooling (`src.comparison`)

The repository provides two dedicated tools in `src/comparison/` for benchmark campaigns and cross-solver Excel comparisons:

### 3.1 CaDiCaL Log Parser (`cadical_log_parser.py`)

Parses raw CaDiCaL `.out` logs wrapped with `runlim` from [AntiBandwidthSCL](https://github.com/TruongXuanHieu-H/AntiBandwidthSCL.git) and compiles them into the standardized 11-column `summary.csv`.

**Example:**

```bash
python -m src.comparison.cadical_log_parser -i build/symmetry-breaking-mode-f -o benchmarks/cadical/f/summary.csv
```

---

### 3.2 Excel Comparator (`excel_comparator.py`)

Ingests summary CSVs across solvers and symmetry breaking modes (`n`, `f`, `h`, `l`) and generates a unified multi-mode, multi-tab Microsoft Excel (`.xlsx`) workbook.

#### Layout Structure per Symmetry Mode:
- **Instance Metadata (5 columns)**: `Instance`, `n`, `m`, `Lower Bound`, `Upper Bound`.
- **Kissat 4.0.4 (3 columns)**: `Optimal w`, `Time (s)`, `Status`.
- **CaDiCaL 3.0.0 (3 columns)**: `Optimal w`, `Time (s)`, `Status`.
- **CaDiCal 1.2.1 (3 columns)**: `Optimal w`, `Time (s)`, `Status`.

#### Arguments:

| Flag | Long Option | Type | Default | Description |
| :--- | :--- | :---: | :---: | :--- |
| | `--kissat404-f`, `--kissat-f` | `Path` | `None` | Path to Kissat 4.0.4 summary CSV for mode `f`. |
| | `--cadical300-f` | `Path` | `None` | Path to CaDiCaL 3.0.0 summary CSV for mode `f`. |
| | `--cadical121-f`, `--cadical-f` | `Path` | `None` | Path to CaDiCal 1.2.1 summary CSV for mode `f`. |
| | `--kissat404-h`, `--kissat-h` | `Path` | `None` | Path to Kissat 4.0.4 summary CSV for mode `h`. |
| | `--cadical300-h` | `Path` | `None` | Path to CaDiCaL 3.0.0 summary CSV for mode `h`. |
| | `--cadical121-h`, `--cadical-h` | `Path` | `None` | Path to CaDiCal 1.2.1 summary CSV for mode `h`. |
| | `--kissat404-dir`, `--kissat-dir` | `Path` | `None` | Directory containing Kissat summary CSVs. |
| | `--cadical300-dir` | `Path` | `None` | Directory containing CaDiCaL 3.0.0 summary CSVs. |
| | `--cadical121-dir`, `--cadical-dir` | `Path` | `None` | Directory containing CaDiCal 1.2.1 summary CSVs. |
| `-o` | `--output-xlsx` | `Path` | `AntiBandwidth_Comparison.xlsx` | Output Excel workbook file path. |
| | `--title` | `str` | `Comparison` | Title of main comparison worksheet. |
| `-h` | `--help` | | | Show help message and exit. |

#### Complete 3-Way Workflow Example:

```bash
# 1. Run Kissat 4.0.4 Campaign for mode h
python -m src.automation -i instances -o benchmarks/kissat/h -S kissat404 -s h -t 1800 -m 30 --skip-existing

# 2. Run CaDiCaL 3.0.0 Campaign for mode h
python -m src.automation -i instances -o benchmarks/cadical300/h -S cadical300 -s h -t 1800 -m 30 --skip-existing

# 3. Generate 3-Way Comparison Workbook
python -m src.comparison.excel_comparator \
  --kissat404-dir benchmarks/kissat \
  --cadical300-dir benchmarks/cadical300 \
  --cadical121-dir benchmarks/cadical \
  -o AntiBandwidth_Comparison.xlsx
```
