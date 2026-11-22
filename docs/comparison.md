# Cross-Solver Anti-Bandwidth Benchmark Comparison: Kissat 4.0.4 vs CaDiCaL 1.2.1

This document describes the cross-solver benchmarking methodology, metrics, and automated tooling used to evaluate the **Anti-Bandwidth Problem (ABP)** Sequential Counter Ladder (SCL) formulation across two distinct SAT solver implementations:

1. **Kissat 4.0.4 (`kissat404`)**: Python implementation in this repository, powered by **PySAT**.
2. **CaDiCaL 1.2.1**: The native C++ reference implementation from [AntiBandwidthSCL](https://github.com/TruongXuanHieu-H/AntiBandwidthSCL.git).

For details on problem formulation and SCL ladder encoding mathematics, refer to [docs/encoding.md](encoding.md). For details on symmetry breaking modes (`n`, `f`, `h`, `l`), refer to [README.md#symmetry-breaking-modes](../README.md#symmetry-breaking-modes).

---

## 1. Benchmarking Setup & Metric Parity

Both solvers evaluate the standard 24 Matrix Market benchmark graph instances from Markus Sinnl (2018) under identical experimental constraints:

- **Hardware Platform**: Linux x86_64 single-threaded execution.
- **Resource Constraints**:
  - Wall-clock time limit: **1,800.0 seconds** (30 minutes) per graph instance.
  - Memory limit: **30.0 GB** per decision step.
- **Search Strategy**: Incremental linear search from published lower bound $LB$ upward towards upper bound $UB$, terminating upon the first `UNSAT` decision or early exit at $UB$.

### 1.1 Metric Parity

To ensure an unbiased side-by-side comparison between an interpreted Python runner (PySAT) and a compiled C++ binary:

| Dimension | Kissat 4.0.4 (PySAT) | CaDiCaL 1.2.1 (Native C++) |
| :--- | :--- | :--- |
| **Execution Wrapping** | In-process Python with `resource.RLIMIT_AS` isolation | External process managed via `runlim` (`runlim --time=1800 --real=1800 --space=30000`) |
| **`total_time_s`** | Cumulative wall-clock search time (`res.total_time` via `time.perf_counter()`) | Cumulative wall-clock search time (`[runlim] real: <sec>`) |
| **Optimal Bandwidth $w^*$** | Highest feasible bandwidth proved SAT before timeout / UNSAT | Highest feasible bandwidth proved SAT before timeout / UNSAT |
| **Search Status** | `OPTIMAL`, `TIMEOUT`, `MEMOUT`, `UNSAT_START`, `ERROR` | `OPTIMAL`, `TIMEOUT`, `MEMOUT`, `UNSAT`, `ERROR` |
| **Certificate Verification** | Independent certificate verification via `SolutionVerifier` | Internal assignment validation |

### 1.2 Standard 11-Column CSV Schema

Both solvers produce (or are parsed into) a standardized 11-column `summary.csv`:

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

When comparing Kissat 4.0.4 and CaDiCaL 1.2.1 on an instance within a symmetry breaking mode:

1. **Bandwidth Superiority ($w^*$)**:
   The solver that discovers a strictly higher feasible bandwidth $w^*$ is considered the superior solver for that instance.
2. **Status Superiority**:
   If both solvers achieve the same $w^*$, proving `OPTIMAL` (by proving $w^* + 1$ is `UNSAT` or early exiting at $UB$) beats `TIMEOUT` or `MEMOUT`.
3. **Runtime Tie-Breaker**:
   If both solvers prove `OPTIMAL` with identical $w^*$, the solver with the faster wall-clock runtime (`total_time_s`) is superior (threshold: $\Delta t > 0.005\text{ s}$).
4. **Strict Timeout Tie Rule**:
   If both solvers time out (`TIMEOUT`) at the same bandwidth $w^*$ (or both timeout before finding any SAT step), neither solver demonstrated superiority.

---

## 3. Comparison Tooling (`src.comparison`)

The repository provides two dedicated tools in `src/comparison/` for ingesting CaDiCaL benchmark logs and compiling cross-solver Excel comparisons:

### 3.1 CaDiCaL Log Parser (`cadical_log_parser.py`)

Parses raw CaDiCaL `.out` logs wrapped with `runlim` from [AntiBandwidthSCL](https://github.com/TruongXuanHieu-H/AntiBandwidthSCL.git) and compiles them into the standardized 11-column `summary.csv`.

**Key Capabilities:**
- Extracts step results, bounds, per-step runtimes, and status.
- Extracts `[runlim] real: <sec>` wall-clock time.
- **Analytical Edge Deduction**: When instance header files are unavailable, calculates edge count $m$ using the exact SCL sliding window clause count formula:
  $$m = \frac{C_{\text{glue}}}{e(n, w)}$$
  where $C_{\text{glue}}$ is the count of glue clauses and $e(n, w)$ is the theoretical clause count per edge.

**Arguments:**

| Flag | Long Option | Type | Default | Description |
| :--- | :--- | :---: | :---: | :--- |
| `-i` | `--input-dir` | `Path` | *required* | Directory containing CaDiCaL `.out` log files (wrapped with `runlim`). |
| `-o` | `--output-csv` | `Path` | `<input-dir>/summary.csv` | Destination path for the generated summary CSV file. |
| `-s` | `--sym-mode` | `choice` | *auto* | Symmetry breaking mode: `n` (none), `f` (first-vertex), `h` (highest-degree), `l` (lowest-degree). Auto-detected from directory or file names if omitted. |
| | `--instances-dir` | `Path` | `None` | Optional directory containing original benchmark instances (`*.mtx.rnd`) to cross-check graph parameters ($n, m$). |
| `-q` | `--quiet` | `flag` | `False` | Suppress per-file console progress messages. |
| `-h` | `--help` | | | Show help message and exit. |

**Example:**

```bash
python -m src.comparison.cadical_log_parser -i build/symmetry-breaking-mode-f
```

---

### 3.2 Excel Comparator (`excel_comparator.py`)

Ingests Kissat and CaDiCaL summary CSVs across one or more symmetry breaking modes (`n`, `f`, `h`, `l`) and generates a multi-tab Microsoft Excel (`.xlsx`) workbook.

**Arguments:**

| Flag | Long Option | Type | Default | Description |
| :--- | :--- | :---: | :---: | :--- |
| | `--kissat-f` | `Path` | `None` | Path to Kissat summary CSV for symmetry mode `f`. |
| | `--cadical-f` | `Path` | `None` | Path to CaDiCaL summary CSV for symmetry mode `f`. |
| | `--kissat-h` | `Path` | `None` | Path to Kissat summary CSV for symmetry mode `h`. |
| | `--cadical-h` | `Path` | `None` | Path to CaDiCaL summary CSV for symmetry mode `h`. |
| | `--kissat-n` | `Path` | `None` | Path to Kissat summary CSV for symmetry mode `n`. |
| | `--cadical-n` | `Path` | `None` | Path to CaDiCaL summary CSV for symmetry mode `n`. |
| | `--kissat-l` | `Path` | `None` | Path to Kissat summary CSV for symmetry mode `l`. |
| | `--cadical-l` | `Path` | `None` | Path to CaDiCaL summary CSV for symmetry mode `l`. |
| | `--kissat-dir` | `Path` | `None` | Directory containing Kissat summary CSVs (e.g. `summary_mode_f.csv`, `f/summary.csv`). |
| | `--cadical-dir` | `Path` | `None` | Directory containing CaDiCaL summary CSVs (e.g. `cadical_summary_mode_f.csv`, `f/summary.csv`). |
| `-o` | `--output-xlsx` | `Path` | `AntiBandwidth_Comparison.xlsx` | Output Excel workbook file path. |
| | `--title` | `str` | `Comparison` | Title of main comparison worksheet. |
| `-h` | `--help` | | | Show help message and exit. |

**Example:**

```bash
python -m src.comparison.excel_comparator \
  --kissat-f benchmarks/f/summary.csv \
  --cadical-f cadical/f/summary.csv \
  --kissat-h benchmarks/h/summary.csv \
  --cadical-h cadical/h/summary.csv \
  -o comparison_f_and_h.xlsx
```
