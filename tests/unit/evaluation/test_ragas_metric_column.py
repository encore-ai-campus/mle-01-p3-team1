import pandas as pd

from src.evaluation.langgraph.ragas_eval import metric_value


def test_column_with_settings_suffix_is_found():
    row = pd.Series({"faithfulness": 0.9, "factual_correctness(mode=f1)": 0.8})
    assert metric_value(row, "factual_correctness") == 0.8
    assert metric_value(row, "faithfulness") == 0.9


def test_missing_metric_returns_default():
    assert metric_value(pd.Series({"faithfulness": 1.0}), "factual_correctness") == ""
    assert metric_value(pd.Series({"faithfulness": 1.0}), "factual_correctness", None) is None
