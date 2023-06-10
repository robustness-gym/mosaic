from typing import Any, List

from pydantic import BaseModel

from meerkat.dataframe import DataFrame
from meerkat.interactive.app.src.lib.component.abstract import Component
from meerkat.interactive.endpoint import EndpointProperty
from meerkat.interactive.event import EventInterface
from meerkat.interactive.formatter.base import register_placeholder


class OnEditInterface(EventInterface):
    """Defines the interface for an event.

    Subclass this to define the interface for a new event type.
    The class will specify the keyword arguments returned by an event from the
    frontend to any endpoint that has subscribed to it.

    All endpoints that are expected to receive an event of this type should
    ensure they have a signature that matches the keyword arguments defined
    in this class.
    """

    column: str
    keyidx: int
    posidx: int
    value: Any


class Cell(BaseModel):
    column: str
    keyidx: int
    posidx: int
    value: Any


class OnSelectTableCells(EventInterface):
    selected: List[Cell]


class OnSelectTableCols(EventInterface):
    selected: List[str]  # list of column names


class OnSelectTableRows(EventInterface):
    selected: List[int]  # list of keyidx


class Table(Component):
    df: DataFrame
    selected: List[str] = []
    single_select: bool = False
    classes: str = "h-fit"

    on_edit: EndpointProperty[OnEditInterface] = None
    on_select_cells: EndpointProperty[OnSelectTableCells] = None
    on_select_cols: EndpointProperty[OnSelectTableCols] = None
    on_select_rows: EndpointProperty[OnSelectTableRows] = None

    def __init__(
        self,
        df: DataFrame,
        *,
        selected: List[int] = [],
        single_select: bool = False,
        classes: str = "h-fit",
        on_edit: EndpointProperty = None,
        on_select_cells: EndpointProperty = None,
        on_select_cols: EndpointProperty = None,
        on_select_rows: EndpointProperty = None
    ):
        """Table view of a DataFrame.

        Args:
            df (DataFrame): The DataFrame to display.
            selected (List[int], optional): The indices of the rows selected in the \
                gallery. Useful for labeling and other tasks. Defaults to [].
            allow_selection (bool, optional): Whether to allow the user to select \
                rows. Defaults to False.
            single_select: Whether to allow the user to select only one row.
        """
        super().__init__(
            df=df,
            selected=selected,
            single_select=single_select,
            classes=classes,
            on_edit=on_edit,
            on_select_cells=on_select_cells,
            on_select_cols=on_select_cols,
            on_select_rows=on_select_rows,
        )

    def _get_ipython_height(self):
        return "600px"


register_placeholder(
    name="table",
    fallbacks=["thumbnail"],
    description="Formatter to be used in a gallery view.",
)
