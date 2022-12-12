from pydantic import Field
from meerkat.interactive.graph import Store, store_field

from ..abstract import Component


class MultiSelect(Component):

    choices: Store[list]
    selected: Store[list] = Field(default_factory=lambda: Store(list()))
    gui_type: str = "multiselect"
    title: str = None