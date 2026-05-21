"""Sample-pipeline loader — copies the bundled sample into the cwd
and runs it end-to-end. Powers ``litmus demo``.

The sample lives inside the installed package (``litmus/templates/
sample_pipeline/``) so it works both when developing from a git clone
and when the user installed via ``pipx install litmus-data``.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from litmus.pipelines.runner import run_all

# Source-of-truth lives inside the installed package; the repo's
# examples/sample_pipeline/ is a convenience copy for direct dev use.
SAMPLE_ROOT = Path(__file__).parent.parent / "templates" / "sample_pipeline"


def load_sample(warehouse_url: str) -> None:
    """Copy sample CSVs into ./data/raw/ and register the sample pipelines."""
    if not SAMPLE_ROOT.exists():
        raise FileNotFoundError(
            f"Sample pipeline not found at {SAMPLE_ROOT}. "
            "If you cloned a stripped repo, restore examples/sample_pipeline/."
        )

    target_data = Path("data/raw")
    target_data.mkdir(parents=True, exist_ok=True)
    for csv in (SAMPLE_ROOT / "data").glob("*.csv"):
        shutil.copy(csv, target_data / csv.name)

    for sub in ("pipelines", "transforms", "metrics", "dashboards", "semantic"):
        Path(sub).mkdir(exist_ok=True)
        src_sub = SAMPLE_ROOT / sub
        if src_sub.exists():
            for f in src_sub.iterdir():
                if f.is_file():
                    shutil.copy(f, Path(sub) / f.name)

    print("[sample] copied data + pipelines + transforms + metrics + dashboards + semantic")


def run_demo(warehouse_url: str) -> None:
    """Load the sample and run it end-to-end."""
    load_sample(warehouse_url)
    run_all(warehouse_url)
