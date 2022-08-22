"""Unittests for NumpyColumn."""


import numpy as np
import pandas as pd
import pytest
import torch

from meerkat import PandasSeriesColumn
from meerkat.block.tensor_block import TensorBlock

from .abstract import AbstractColumnTestBed, column_parametrize


class PandasSeriesColumnTestBed(AbstractColumnTestBed):

    DEFAULT_CONFIG = {
        "contiguous_index": [True, False],
        "dtype": ["float", "int", "str"],
    }

    marks = pytest.mark.pandas_col

    def __init__(
        self,
        length: int = 16,
        dtype="float",
        contiguous_index: bool = True,
        seed: int = 123,
        tmpdir: str = None,
    ):
        self.dtype = dtype
        np.random.seed(seed)
        array = np.random.random(length) * 10
        series = pd.Series(array).astype(dtype)
        if not contiguous_index:
            series.index = np.arange(1, 1 + 2 * length, 2)

        self.col = PandasSeriesColumn(series)
        self.data = series

    def get_map_spec(
        self,
        batched: bool = True,
        materialize: bool = False,
        salt: int = 1,
        kwarg: int = 0,
    ):
        salt = salt if self.dtype != "str" else str(salt)
        kwarg = kwarg if self.dtype != "str" else str(kwarg)
        return {
            "fn": lambda x, k=0: x + salt + (k if self.dtype != "str" else str(k)),
            "expected_result": PandasSeriesColumn(self.col.data + salt + kwarg),
            "output_type": PandasSeriesColumn,
        }

    def get_filter_spec(
        self,
        batched: bool = True,
        materialize: bool = False,
        salt: int = 1,
        kwarg: int = 0,
    ):
        salt = 3 + salt if self.dtype != "str" else str(3 + salt)
        kwarg = kwarg if self.dtype != "str" else str(kwarg)
        return {
            "fn": lambda x, k=0: x > salt + (k if self.dtype != "str" else str(k)),
            "expected_result": self.col[self.col.data > salt + kwarg],
        }

    def get_data(self, index, materialize: bool = True):
        return self.data.iloc[index]

    def get_data_to_set(self, data_index):
        if isinstance(data_index, int):
            return 0
        return pd.Series(np.zeros_like(self.get_data(data_index).values))

    @staticmethod
    def assert_data_equal(data1: pd.Series, data2: np.ndarray):
        if isinstance(data1, pd.Series):
            assert (data1.values == data2.values).all()
        else:
            assert data1 == data2


@pytest.fixture(**column_parametrize([PandasSeriesColumnTestBed]))
def testbed(request, tmpdir):
    testbed_class, config = request.param
    return testbed_class(**config, tmpdir=tmpdir)


@PandasSeriesColumnTestBed.parametrize({"dtype": ["str"]})
def test_str_accessor(testbed):
    col = testbed.col

    new_col = col.str.split(".").str[0].astype(int)
    assert isinstance(new_col, PandasSeriesColumn)
    assert (new_col == testbed.data.astype(float).astype(int)).all()


def test_dt_accessor():
    col = PandasSeriesColumn(
        data=[f"01/{idx+1}/2001" for idx in range(16)],
    )
    col = pd.to_datetime(col)
    day_col = col.dt.day
    assert isinstance(day_col, PandasSeriesColumn)
    assert (day_col.values == np.arange(16) + 1).all()


def test_cat_accessor():
    categories = ["a", "b", "c", "d"]
    col = PandasSeriesColumn(data=categories * 4)
    col = col.astype("category")

    assert (np.array(categories) == col.cat.categories.values).all()


def test_init_block():
    block_view = TensorBlock(torch.zeros(10, 10))[0]
    with pytest.raises(ValueError):
        PandasSeriesColumn(block_view)


def test_to_tensor(testbed):
    col, _ = testbed.col, testbed.data
    if testbed.dtype == "str":
        with pytest.raises(ValueError):
            col.to_tensor()
    else:
        tensor = col.to_tensor()

        assert torch.is_tensor(tensor)
        assert (col == tensor.numpy()).all()


def test_to_pandas(testbed):
    col, _ = testbed.col, testbed.data
    series = col.to_pandas()
    assert isinstance(series, pd.Series)
    assert (col.data.values == series.values).all()


def test_repr_pandas(testbed):
    series = testbed.col.to_pandas()
    assert isinstance(series, pd.Series)


def test_ufunc_out():
    out = np.zeros(3)
    a = PandasSeriesColumn([1, 2, 3])
    b = PandasSeriesColumn([1, 2, 3])
    np.add(a, b, out=out)
    assert (out == np.array([2, 4, 6])).all()
