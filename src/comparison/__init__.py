"""Cross-solver comparison package for the Anti-Bandwidth Problem."""

import warnings

# Suppress runpy warning when submodules are executed directly via `python -m`
warnings.filterwarnings(
    "ignore",
    message=r".*found in sys\.modules after import of package.*",
    category=RuntimeWarning,
)

from src.comparison.cadical_log_parser import (
    CSV_COLUMNS,
    CadicalLogResult,
    derive_edge_count,
    parse_cadical_directory,
    parse_cadical_log,
)
from src.comparison.excel_comparator import (
    SolverRecord,
    determine_better_solver,
    determine_bold_cells,
    generate_excel_comparison,
    load_csv,
)

__all__ = [
    "CSV_COLUMNS",
    "CadicalLogResult",
    "derive_edge_count",
    "parse_cadical_directory",
    "parse_cadical_log",
    "SolverRecord",
    "determine_better_solver",
    "determine_bold_cells",
    "generate_excel_comparison",
    "load_csv",
]
