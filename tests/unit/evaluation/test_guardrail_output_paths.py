from datetime import datetime

import pytest

from src.guardrails.eval_guardrails import DOC, make_output_path, write_report


def test_guardrail_evalset_is_in_central_datasets():
    assert DOC.parent.name == "guardrails"
    assert DOC.parent.parent.name == "datasets"
    assert DOC.is_file()


def test_report_is_saved_in_a_run_folder_without_overwriting(tmp_path):
    path = make_output_path(tmp_path, datetime(2026, 11, 13, 10, 11, 12))
    write_report(["# 평가"], [], {}, output_path=path)
    assert path.name == "report.md"
    assert path.parent.name.startswith("run_20261113_101112")
    assert path.is_file()
    with pytest.raises(FileExistsError):
        write_report(["# 다른 결과"], [], {}, output_path=path)
