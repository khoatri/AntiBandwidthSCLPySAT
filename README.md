# AntiBandwidthSCLPySAT

A SAT-based solver for the **Anti-Bandwidth Problem (ABP)** using the **SCL encoding (Sequential Counter encoding for Ladder constraints)**, implemented in Python with **PySAT** and the dedicated **Kissat 4.0.4 (`kissat404`)** backend.

Given an undirected graph $G = (V, E)$ with $n = |V|$ vertices, the Anti-Bandwidth Problem seeks a bijective labeling $\phi: V \to \{1, 2, \dots, n\}$ that maximizes the minimum label difference between adjacent vertices:

$$\operatorname{AB}(G) = \max_{\phi} \min_{\{u, v\} \in E} |\phi(u) - \phi(v)|$$

The SCL encoding partitions the vertex-label assignment domain into $K = \lceil n/w \rceil$ blocks, maintains prefix/suffix ladder summaries with the Sequential Counter formulation, and enforces sliding window edge exclusions.

---

## Project Layout

```text
AntiBandwidthSCLPySAT/
├── README.md                      # Project documentation and CLI guide
├── requirements.txt               # Direct Python dependencies
├── pyproject.toml                 # Package metadata and test configurations
├── docs/
│   └── encoding.md                # Exact mathematical SCL formulation and count proofs
├── instances/                     # Matrix Market benchmark graph instances (*.mtx.rnd)
├── benchmarks/                    # Output directory for campaigns (CSV, JSON logs)
└── src/
    ├── cli.py                     # Unified Command-Line Interface (inspect, solve, optimize)
    ├── automation.py              # Batch campaign runner across instances
    ├── encoding/                  # SCL CNF encoding engine
    │   ├── scl_encoder.py         # Main SCL formula assembler and count validator
    │   ├── ladder.py              # Prefix/suffix ladder chains & block occupancy
    │   ├── product_eo.py          # 2-Product Exactly-One & sequential AMO chains
    │   ├── sliding_window.py      # Aligned & crossing window edge exclusions
    │   └── symmetry.py            # Vertex label-reversal symmetry breaking
    ├── solvers/                   # Solver backend and search optimization
    │   ├── solver.py              # PySAT kissat404 wrapper with process isolation
    │   └── optimizer.py           # Incremental linear search engine
    ├── utils/                     # Supporting graph utilities
    │   ├── graph.py               # Graph structure, degrees, and upper bounds
    │   ├── graph_parser.py        # Parser for *.mtx.rnd benchmark format
    │   └── solution_verifier.py   # Independent certificate verifier
    └── tests/                     # 110+ unit and integration tests
```

---

## Getting Started

### Prerequisites

- **Operating System**: Linux (required for process isolation and memory limit enforcement via `resource.RLIMIT_AS`).
- **Python**: Version 3.9 or newer.

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/khoatri/AntiBandwidthSCLPySAT.git
   cd AntiBandwidthSCLPySAT
   ```

2. Create and activate a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install the dependencies:
   ```bash
   pip install -r requirements.txt
   pip install -e .
   ```

### Running the Test Suite

Execute the test suite across all modules:

```bash
pytest -v
```

---

## Command-Line Interface (CLI)

### 1. Main CLI (`src.cli`)

The main CLI is accessible via `python -m src.cli [subcommand] [options]`.

#### 1.1. `inspect` Subcommand

Profiles graph properties and calculates exact theoretical SCL formula dimensions ($N$ variables, $C$ clauses) in $< 1\text{ ms}$ without invoking the SAT solver.

**Arguments:**

| Flag | Long Option | Type | Default | Description |
| :--- | :--- | :---: | :---: | :--- |
| `-g` | `--graph` | `str` | *required* | Path to input graph instance file (`*.mtx.rnd`). |
| `-w` | `--width` | `int` | `2` | Target bandwidth threshold $w$ for theoretical formula sizing ($2 \le w \le n$). |
| `-s` | `--sym` | `choice` | `n` | Symmetry breaking mode: `n` (none), `f` (first-vertex), `h` (half/max-degree), `l` (lowest-degree). |
| `-h` | `--help` | | | Show help message and exit. |

**Example:**

```bash
python -m src.cli inspect -g instances/A-pores_1.mtx.rnd -w 6 -s h
```

---

#### 1.2. `solve` Subcommand

Solves a single decision problem instance: **Is $\operatorname{AB}(G) \ge w$?** Returns `SAT`, `UNSAT`, `TIMEOUT`, `MEMOUT`, or `ERROR`. Every satisfiable solution is verified at runtime against domain bijectivity and distance constraints.

**Arguments:**

| Flag | Long Option | Type | Default | Description |
| :--- | :--- | :---: | :---: | :--- |
| `-g` | `--graph` | `str` | *required* | Path to input graph instance file (`*.mtx.rnd`). |
| `-w` | `--width` | `int` | *required* | Target bandwidth threshold $w$ ($2 \le w \le n$). |
| `-s` | `--sym` | `choice` | `n` | Symmetry breaking mode: `n`, `f`, `h`, or `l`. |
| `-t` | `--timeout` | `float` | `None` | Maximum solve time limit in seconds. |
| `-m` | `--mem-limit` | `float` | `None` | Maximum memory limit in **GB** per solve step (e.g. `30.0`). |
| `-o` | `--output` | `str` | `None` | Path to save JSON result. Accepts a specific file (`result.json`) or a directory (`/tmp/`), which writes `<instance_name>.json`. |
| `-q` | `--quiet` | `flag` | `False` | Suppress human-readable console output. |
| `-h` | `--help` | | | Show help message and exit. |

**Example:**

```bash
python -m src.cli solve -g instances/A-pores_1.mtx.rnd -w 6 -s h -t 30.0 -m 30.0 -o /tmp/
```

---

#### 1.3. `optimize` Subcommand

Finds the optimal anti-bandwidth $w^*$ via incremental linear search ($w = start\_w, start\_w + 1, \dots$), terminating at the first `UNSAT` result or early exiting at the theoretical upper bound $U = \lfloor n/2 \rfloor$. Enforces total cumulative instance timeout across search steps.

**Arguments:**

| Flag | Long Option | Type | Default | Description |
| :--- | :--- | :---: | :---: | :--- |
| `-g` | `--graph` | `str` | *required* | Path to input graph instance file (`*.mtx.rnd`). |
| | `--start-w` | `int` | `2` | Starting lower bound for search ($\ge 2$). |
| `-s` | `--sym` | `choice` | `n` | Symmetry breaking mode: `n`, `f`, `h`, or `l`. |
| `-t` | `--timeout` | `float` | `None` | Total maximum time in seconds for the entire optimization search. |
| `-m` | `--mem-limit` | `float` | `None` | Maximum memory limit in **GB** per decision step (e.g. `30.0`). |
| `-o` | `--output` | `str` | `None` | Path to export optimization results to JSON (file path or directory). |
| `-q` | `--quiet` | `flag` | `False` | Suppress progress prints to console. |
| `-h` | `--help` | | | Show help message and exit. |

**Example:**

```bash
python -m src.cli optimize -g instances/A-pores_1.mtx.rnd --start-w 4 -s h -t 300.0 -m 30.0 -o benchmarks/results/
```

---

### 2. Batch Benchmark Automation (`src.automation`)

Runs benchmark campaigns across all matching instances in `instances/`, streams summary progress live to `benchmarks/summary.csv`, records metadata in `benchmarks/campaign_manifest.json`, and saves per-instance JSON logs in `benchmarks/results/`. Runs strictly single-threaded to ensure deterministic, reproducible benchmarks.

```bash
python -m src.automation [options]
```

**Arguments:**

| Flag | Long Option | Type | Default | Description |
| :--- | :--- | :---: | :---: | :--- |
| `-i` | `--instances-dir` | `str` | `"instances"` | Directory containing benchmark graph instances (`*.mtx.rnd`). |
| `-o` | `--output-dir` | `str` | `"benchmarks"` | Output directory where `summary.csv`, manifest, and `results/` are stored. |
| `-s` | `--sym` | `choice` | `n` | Symmetry breaking mode applied across the campaign (`n`, `f`, `h`, `l`). |
| `-t` | `--timeout` | `float` | `1800.0` | Total timeout in seconds per instance for linear search. |
| `-m` | `--mem-limit` | `float` | `30.0` | Maximum memory limit in **GB** per decision step. |
| | `--skip-existing` | `flag` | `False` | Skip instances that already have completed JSON output in `output_dir/results`. |
| | `--start-w-mode` | `choice` | `default` | Starting lower bound mode: `'default'` (starts at 2) or `'best_known'` (starts at header's `best_known_w`). |
| `-q` | `--quiet` | `flag` | `False` | Suppress per-instance console progress logs. |
| `-h` | `--help` | | | Show help message and exit. |

**Example:**

```bash
python -m src.automation -i instances -o benchmarks -s h -t 1800 -m 30 --skip-existing
```

#### `summary.csv` Columns

The `summary.csv` file is streamed and flushed row-by-row live as each instance finishes:

| Column | Description | Example |
| :--- | :--- | :--- |
| `instance` | Filename of the benchmark graph instance. | `A-pores_1.mtx.rnd` |
| `n` | Number of vertices $\|V\|$. | `30` |
| `m` | Number of edges $\|E\|$. | `103` |
| `best_known_w` | Best known bandwidth recorded in instance header. | `7` |
| `optimal_w` | Maximum feasible bandwidth $w^*$ discovered. | `6` |
| `status` | Search outcome: `OPTIMAL`, `TIMEOUT`, `MEMOUT`, `UNSAT_START`, or `ERROR`. | `OPTIMAL` |
| `total_time_s` | Cumulative search time in seconds across all steps. | `0.297` |
| `steps_evaluated` | Number of sequential linear search steps tested. | `3` |
| `sym_mode` | Symmetry breaking mode used (`n`, `f`, `h`, `l`). | `h` |
| `verified` | Solution certificate verification boolean (`True`/`False`). | `True` |

---

## Symmetry Breaking Modes

The Anti-Bandwidth Problem exhibits label-reversal symmetry: for any valid labeling $\phi$, its mirror $\phi'(v) = n + 1 - \phi(v)$ preserves all pairwise absolute label distances $|\phi'(u) - \phi'(v)| = |\phi(u) - \phi(v)|$. 

Symmetry breaking eliminates this duality by enforcing $\phi(s) \le \lceil n/2 \rceil$ on a chosen vertex $s$:

| Mode | Name | Vertex $s$ Selection | Unit Clauses Added |
| :---: | :--- | :--- | :--- |
| `n` | None | No symmetry breaking applied. | $0$ |
| `f` | First-vertex | $s = 1$ (first vertex in graph). | $\lfloor n/2 \rfloor$ clauses $\neg A_{1, \ell}$ for $\ell > \lceil n/2 \rceil$ |
| `h` | Half-degree (Max) | $s = \operatorname{argmax}_{v} \operatorname{deg}(v)$, breaking ties by lowest vertex index. | $\lfloor n/2 \rfloor$ clauses $\neg A_{s, \ell}$ for $\ell > \lceil n/2 \rceil$ |
| `l` | Lowest-degree (Min) | $s = \operatorname{argmin}_{v} \operatorname{deg}(v)$, breaking ties by lowest vertex index. | $\lfloor n/2 \rfloor$ clauses $\neg A_{s, \ell}$ for $\ell > \lceil n/2 \rceil$ |
