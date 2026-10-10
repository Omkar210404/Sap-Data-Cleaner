import pandas as pd
import pytest

from sap_cleaner.runlog import RunLog


@pytest.fixture
def log():
    return RunLog()


@pytest.fixture
def make_df():
    """Build an all-text DataFrame indexed like the pipeline's input.

    The index is the source row number: the header is row 1, so data starts at 2.
    """
    def _make(rows):
        df = pd.DataFrame(rows, dtype=str)
        df.index = range(2, len(df) + 2)
        return df
    return _make
