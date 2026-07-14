import json
from pathlib import Path

import pandas as pd

from etl.dedup import assign_groups
from etl.lint import lint_frame
from etl.quality import score_frame
from etl.report import write_report

FIXTURE = Path(__file__).parent / "fixtures" / "recipes_fixture.json"


def test_end_to_end_report_on_fixture(tmp_path):
    df = pd.DataFrame(json.loads(FIXTURE.read_text()))
    df = score_frame(assign_groups(lint_frame(df)))
    out = tmp_path / "report.md"
    write_report(df, out)
    text = out.read_text()
    for section in ["# Phase 0 Corpus Report", "## Lint", "## Dedup", "## Quality"]:
        assert section in text
    assert "unused_ingredient" in text  # planted defect surfaces in the report
