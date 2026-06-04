"""dataframe_to_str_dict_records — nullable Int64 safe export."""

import pandas as pd

from data_access.dtype_normalization import dataframe_to_str_dict_records


def test_dataframe_to_str_dict_records_nullable_int64():
    df = pd.DataFrame({"Week": pd.array([1, None], dtype="Int64"), "Team": ["A", "B"]})
    rows = dataframe_to_str_dict_records(df)
    assert rows[0]["Week"] == "1"
    assert rows[1]["Week"] == ""
