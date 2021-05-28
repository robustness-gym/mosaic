import collections.abc
from typing import List, Sequence, Union

import numpy as np

from mosaic import DataPanel, ListColumn
from mosaic.columns.cell_column import CellColumn
from mosaic.columns.numpy_column import NumpyArrayColumn
from mosaic.columns.tensor_column import TensorColumn
from mosaic.errors import MergeError


def merge(
    left: DataPanel,
    right: DataPanel,
    how: str = "inner",
    on: Union[str, List[str]] = None,
    left_on: Union[str, List[str]] = None,
    right_on: Union[str, List[str]] = None,
    sort: bool = False,
    suffixes: Sequence[str] = ("_x", "_y"),
    validate=None,
    keep_indexes: bool = False,
):
    if how == "cross":
        raise ValueError("DataPanel does not support cross merges.")

    if (on is None) and (left_on is None) and (right_on is None):
        raise ValueError("Merge expects either `on` or `left_on` and `right_on`")
    left_on = on if left_on is None else left_on
    right_on = on if right_on is None else right_on

    # ensure we can merge on specified columns
    _check_merge_columns(left, left_on)
    _check_merge_columns(right, right_on)

    # convert datapanels to dataframes so we can apply Pandas merge
    # (1) only include columns we are joining on
    left_on = [left_on] if isinstance(left_on, str) else left_on
    right_on = [right_on] if isinstance(right_on, str) else right_on
    left_df = left[left_on].to_pandas()
    right_df = right[right_on].to_pandas()
    # (2) add index columns, which we'll use to reconstruct the columns we excluded from
    # the Pandas merge
    if ("__right_indices__" in right_df) or ("__left_indices__" in left_df):
        raise ValueError("The column names '__right_indices__' and ")
    left_df["__left_indices__"] = np.arange(len(left_df))
    right_df["__right_indices__"] = np.arange(len(right_df))

    # apply pandas merge
    merged_df = left_df.merge(
        right_df,
        how=how,
        left_on=left_on,
        right_on=right_on,
        sort=sort,
        validate=validate,
        suffixes=suffixes,
    )
    left_indices = merged_df.pop("__left_indices__").values
    right_indices = merged_df.pop("__right_indices__").values

    # reconstruct other columns not in the `left_on | right_on` using `left_indices`
    # and `right_indices`, the row order returned by merge
    merged_df = merged_df[set(left_on) | set(right_on)]
    new_dps = []
    for indices, dp in [(left_indices, left), (right_indices, right)]:
        cols_to_create = [k for k in dp.keys() if k not in merged_df]
        if np.isnan(indices).any():
            # when performing "outer", "left", and "right" merges, column indices output
            # by pandas merge can include `nan` in rows corresponding to merge keys that
            # only appear in one of the two frames. For these columns, we convert the
            # column to  ListColumn, and fill with "None" wherever indices is "nan".
            data = {
                name: ListColumn(
                    [
                        None if np.isnan(index) else col.lz[int(index)]
                        for index in indices
                    ]
                )
                for name, col in dp.items()
                if name in cols_to_create
            }
            new_dp = DataPanel.from_batch(data)
        else:
            # if there are no `nan`s in the indices, then we can just lazy index the
            # original column
            new_dp = dp[cols_to_create].lz[indices]
        new_dps.append(new_dp)

    # concatenate the three datapanels (1) reconstructed from left indices,
    # (2) reconstructed from right indices, (3) created out of the output of pandas
    # merge
    merged_dp = new_dps[0].append(new_dps[1], axis="columns", suffixes=suffixes)
    merged_dp = DataPanel.from_pandas(merged_df).append(
        merged_dp, axis="columns", overwrite=True
    )

    if not keep_indexes:
        merged_dp.remove_column("index" + suffixes[0])
        merged_dp.remove_column("index" + suffixes[1])

    return merged_dp


def _check_merge_columns(dp: DataPanel, on: List[str]):
    for name in on:
        column = dp[name]
        if isinstance(column, NumpyArrayColumn) or isinstance(column, TensorColumn):
            if len(column.shape) > 1:
                raise MergeError(
                    f"Cannot merge on column `{name}`, has more than one dimension."
                )
        elif isinstance(column, ListColumn):
            if not all(
                [isinstance(cell, collections.abc.Hashable) for cell in column.lz]
            ):
                raise MergeError(
                    f"Cannot merge on column `{name}`, contains unhashable objects."
                )

        elif isinstance(column, CellColumn):
            if not all(
                [isinstance(cell, collections.abc.Hashable) for cell in column.lz]
            ):
                raise MergeError(
                    f"Cannot merge on column `{name}`, contains unhashable cells."
                )
