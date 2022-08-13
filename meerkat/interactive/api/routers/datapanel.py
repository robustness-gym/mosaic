import functools
from ctypes import Union
from multiprocessing.sharedctypes import Value
from time import sleep
from typing import Any, Dict, List

import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import meerkat as mk
from meerkat.datapanel import DataPanel
from meerkat.state import state


def get_datapanel(datapanel_id: str):
    try:
        if datapanel_id == "test-imagenette":
            return mk.get("imagenette", version="320px")

        datapanel = state.identifiables.datapanels[datapanel_id]

    except KeyError:
        raise HTTPException(
            status_code=404, detail="No datapanel with id {}".format(datapanel_id)
        )
    return datapanel


router = APIRouter(
    prefix="/dp",
    tags=["dp"],
    responses={404: {"description": "Not found"}},
)


class ColumnInfo(BaseModel):

    name: str
    type: str
    cell_component: str
    cell_props: Dict[str, Any]


class SchemaRequest(BaseModel):
    columns: List[str] = None


class SchemaResponse(BaseModel):
    id: str
    columns: List[ColumnInfo]


@router.post("/{datapanel_id}/schema/")
def get_schema(datapanel_id: str, request: SchemaRequest) -> SchemaResponse:
    dp = get_datapanel(datapanel_id)
    columns = dp.columns if request is None else request.columns
    return SchemaResponse(id=datapanel_id, columns=_get_column_infos(dp, columns))


def _get_column_infos(dp: DataPanel, columns: List[str] = None):
    if columns is None:
        columns = dp.columns
    else:
        missing_columns = set(columns) - set(dp.columns)
        if len(missing_columns) > 0:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Requested columns {columns} do not exist in datapanel"
                    f" with id {dp.id}"
                ),
            )

    # TODO: remove this and fix
    columns = [column for column in columns if column != "clip(img)"]

    return [
        ColumnInfo(
            name=col,
            type=type(dp[col]).__name__,
            cell_component=dp[col].formatter.cell_component,
            cell_props=dp[col].formatter.cell_props,
        )
        for col in columns
    ]


class RowsResponse(BaseModel):
    column_infos: List[ColumnInfo]
    indices: List[int] = None
    rows: List[List[Any]]
    full_length: int


class RowsRequest(BaseModel):
    # TODO (sabri): add support for data validation
    start: int = None
    end: int = None
    indices: List[int] = None
    columns: List[str] = None


@router.post("/{datapanel_id}/rows/")
def get_rows(
    datapanel_id: str,
    request: RowsRequest,
) -> RowsResponse:
    """Get rows from a DataPanel as a JSON object."""
    dp = get_datapanel(datapanel_id)
    full_length = len(dp)
    column_infos = _get_column_infos(dp, request.columns)

    dp = dp[[info.name for info in column_infos]]

    if request.indices is not None:
        dp = dp.lz[request.indices]
        indices = request.indices
    elif request.start is not None:
        if request.end is None:
            request.end = len(dp)
        dp = dp.lz[request.start : request.end]
        indices = list(range(request.start, request.end))
    else:
        raise ValueError()

    rows = []
    for row in dp.lz:
        rows.append(
            [dp[info.name].formatter.encode(row[info.name]) for info in column_infos]
        )
    return RowsResponse(
        column_infos=column_infos,
        rows=rows,
        full_length=full_length,
        indices=indices,
    )


class MatchRequest(BaseModel):
    input: str  # The name of the input column.
    query: str  # The query text to match against.


@router.post("/{datapanel_id}/match")
def match(datapanel_id: str, request: MatchRequest) -> SchemaResponse:
    dp = get_datapanel(datapanel_id)
    # write the query to a file
    with open("/tmp/query.txt", "w") as f:
        f.write(request.query)
    try:
        dp, match_columns = mk.match(
            data=dp, query=request.query, input=request.input, return_column_names=True
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return SchemaResponse(id=datapanel_id, columns=_get_column_infos(dp, match_columns))


class SortRequest(BaseModel):
    by: str


# TODO: (Sabri/Arjun) Make this more robust and less hacky
curr_dp: mk.DataPanel = None


@router.post("/{datapanel_id}/sort")
def sort(datapanel_id: str, request: SortRequest) -> SchemaResponse:
    dp = get_datapanel(datapanel_id)
    dp = mk.sort(data=dp, by=request.by, ascending=False)
    global curr_dp
    curr_dp = dp
    return SchemaResponse(id=dp.id, columns=_get_column_infos(dp))


# TODO: Filter to take filtering criteria objects
# TODO: update for filtering row
class FilterRequest(BaseModel):
    columns: List[str]
    values: List[Any]
    ops: List[str]


# Map a string operator to a function that takes a value and returns a boolean.
_operator_str_to_func = {
    "==": lambda x, y: x == y,  # equality
    "!=": lambda x, y: x != y,  # inequality
    ">": lambda x, y: x > y,  # greater than
    "<": lambda x, y: x < y,  # less than
    ">=": lambda x, y: x >= y,  # greater than or equal to
    "<=": lambda x, y: x <= y,  # less than or equal to
    "in": lambda x, y: x in y,  # in
    "not in": lambda x, y: x not in y,  # not in
}


@router.post("/{datapanel_id}/filter")
def filter(datapanel_id: str, request: FilterRequest) -> SchemaResponse:
    dp = get_datapanel(datapanel_id)

    supported_column_types = (mk.PandasSeriesColumn, mk.NumpyArrayColumn)
    if not all(
        isinstance(dp[column], supported_column_types) for column in request.columns
    ):
        raise HTTPException(
            f"Only {supported_column_types} are supported for filtering."
        )

    # Filter pandas series columns.
    all_series = [
        _operator_str_to_func[op](dp[col], value)
        for col, value, op in zip(request.columns, request.values, request.ops)
    ]
    mask = functools.reduce(lambda x, y: x & y, all_series)
    dp = dp.lz[mask]

    global curr_dp
    curr_dp = dp
    return SchemaResponse(
        id=dp.id, columns=_get_column_infos(dp, ["img", "path", "label"])
    )
