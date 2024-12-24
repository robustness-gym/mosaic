from __future__ import annotations

import collections
from abc import ABC, abstractmethod, abstractproperty
from typing import TYPE_CHECKING, Any, Dict, Iterator, List, Type, Union

import yaml

from meerkat.columns.deferred.base import DeferredCell
from meerkat.tools.utils import MeerkatDumper, MeerkatLoader

if TYPE_CHECKING:
    from meerkat.interactive.app.src.lib.component.abstract import BaseComponent


class Variant:
    def __init__(*args, **kwargs):
        pass


class FormatterGroup(collections.abc.Mapping):
    """A formatter group is a mapping from formatter placeholders to
    formatters.

    Data in a Meerkat column sometimes need to be displayed differently in different
    GUI contexts. For example, in a table, we display thumbnails of images, but in a
    carousel view, we display the full image.

    Because most components in Meerkat work on any data type, it is important that
    they are implemented in a formatter-agnostic way. So, instead of specifying
    formatters, components make requests for data specifying a *formatter placeholder*.
    For example, the {class}`mk.gui.Gallery` component requests data using the
    `thumbnail` formatter placeholder.

    For a specific column of data, we specify which formatters to use for each
    placeholder using a *formatter group*. A formatter group is a mapping from
    formatter placeholders to formatters. Each column in Meerkat has a
    `formatter_group` property. A column's formatter group controls how it will be
    displayed in different contexts in Meerkat GUIs.

    Args:
        base (FormatterGroup): The base formatter group to use.
        **kwargs: The formatters to add to the formatter group.
    """

    def __init__(self, base: BaseFormatter = None, **kwargs):
        if base is None:
            from meerkat.interactive.formatter import TextFormatter

            # everything has a str method so this is a safe default
            base = TextFormatter()

        if not isinstance(base, BaseFormatter):
            raise TypeError("base must be a Formatter")
        for key, value in kwargs.items():
            if key not in formatter_placeholders:
                raise ValueError(
                    f"The key {key} is not a registered formatter "
                    "placeholder. Use `mk.register_formatter_placeholder`"
                )
            if not isinstance(value, BaseFormatter):
                raise TypeError(
                    f"FormatterGroup values must be Formatters, not {type(value)}"
                )

        # must provide a base formatter
        self._dict = dict(base=base, **kwargs)

    def __getitem__(self, key: Union[FormatterPlaceholder, str]) -> BaseFormatter:
        """Get the formatter for the given formatter placeholder.

        Args:
            key (FormatterPlaceholder): The formatter placeholder.

        Returns:
            (Formatter) The formatter for the formatter placeholder.
        """
        if isinstance(key, str):
            if key in formatter_placeholders:
                key = formatter_placeholders[key]
            else:
                key = FormatterPlaceholder(key, [])

        if key.name in self._dict:
            return self._dict.__getitem__(key.name)
        for fallback in key.fallbacks:
            if fallback.name in self._dict:
                return self.__getitem__(fallback)
        return self._dict["base"]

    def __setitem__(
        self, key: Union[FormatterPlaceholder, str], value: BaseFormatter
    ) -> None:
        if key not in formatter_placeholders:
            raise ValueError(
                f"The key {key} is not a registered formatter "
                "placeholder. Use `mk.register_formatter_placeholder`"
            )
        if not isinstance(value, BaseFormatter):
            raise TypeError(
                f"FormatterGroup values must be Formatters, not {type(value)}"
            )
        return self._dict.__setitem__(key, value)

    def defer(self):
        return deferred_formatter_group(self)

    def __len__(self) -> int:
        return len(self._dict)

    def __iter__(self) -> Iterator:
        return iter(self._dict)

    def update(self, other: Union[FormatterGroup, Dict]):
        self._dict.update(other)

    def copy(self):
        new = self.__class__.__new__(self.__class__)
        new._dict = self._dict.copy()
        return new

    @staticmethod
    def to_yaml(dumper: yaml.Dumper, data: BaseFormatter):
        """This function is called by the YAML dumper to convert a
        :class:`Formatter` object into a YAML node.

        It should not be called directly.
        """
        data = {
            "class": type(data),
            "dict": data._dict,
        }
        return dumper.represent_mapping("!FormatterGroup", data)

    @staticmethod
    def from_yaml(loader, node):
        """This function is called by the YAML loader to convert a YAML node
        into an :class:`Formatter` object.

        It should not be called directly.
        """
        data = loader.construct_mapping(node)
        formatter = data["class"].__new__(data["class"])
        formatter._dict = data["dict"]
        return formatter


MeerkatDumper.add_multi_representer(FormatterGroup, FormatterGroup.to_yaml)
MeerkatLoader.add_constructor("!FormatterGroup", FormatterGroup.from_yaml)


def deferred_formatter_group(group: FormatterGroup) -> FormatterGroup:
    """Wrap all formatters in a FormatterGroup with a DeferredFormatter.

    Args:
        group (FormatterGroup): The FormatterGroup to wrap.

    Returns:
        (FormatterGroup) A new FormatterGroup with all formatters wrapped in a
            DeferredFormatter.
    """
    new_group = group.copy()
    for name, formatter in group.items():
        new_group[name] = DeferredFormatter(formatter)
    return new_group


class FormatterPlaceholder:
    def __init__(
        self,
        name: str,
        fallbacks: List[Union[str, FormatterPlaceholder]],
        description: str = "",
    ):
        global formatter_placeholders
        self.name = name
        self.fallbacks = [
            fb if isinstance(fb, FormatterPlaceholder) else formatter_placeholders[fb]
            for fb in fallbacks
        ]

        if name != "base":
            self.fallbacks.append(FormatterPlaceholder("base", fallbacks=[]))

        self.description = description


formatter_placeholders = {
    "base": FormatterPlaceholder("base", []),
}


def register_placeholder(
    name: str, fallbacks: List[FormatterPlaceholder] = [], description: str = ""
):
    """Register a new formatter placeholder.

    Args:
        name (str): The name of the formatter placeholder.
        fallbacks (List[FormatterPlaceholder]): The fallbacks for the formatter
            placeholder.
        description (str): A description of the formatter placeholder.
    """
    if name in formatter_placeholders:
        raise ValueError(f"{name} is already a registered formatter placeholder")
    formatter_placeholders[name] = FormatterPlaceholder(
        name=name, fallbacks=fallbacks, description=description
    )


# register core formatter placeholders
register_placeholder("small", fallbacks=[], description="A small version of the data.")
register_placeholder(
    "tiny", fallbacks=["small"], description="A tiny version of the data."
)
register_placeholder(
    "thumbnail", fallbacks=["small"], description="A thumbnail of the data."
)
register_placeholder(
    "icon", fallbacks=["tiny"], description="An icon representing the data."
)
register_placeholder(
    "tag",
    fallbacks=["tiny"],
    description="A small version of the data meant to go in a tag field.",
)
register_placeholder(
    "full",
    fallbacks=["base"],
    description="A full version of the data.",
)


class BaseFormatter(ABC):
    component_class: Type["BaseComponent"]
    data_prop: str = "data"
    static_encode: bool = False

    def encode(self, cell: Any, **kwargs):
        """Encode the cell on the backend before sending it to the frontend.

        The cell is lazily loaded, so when used on a LambdaColumn,
        ``cell`` will be a ``LambdaCell``. This is important for
        displays that don't actually need to apply the lambda in order
        to display the value.
        """
        return cell

    @abstractproperty
    def props(self):
        return self._props

    @abstractmethod
    def _get_state(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    def _set_state(self, state: Dict[str, Any]):
        pass

    @staticmethod
    def to_yaml(dumper: yaml.Dumper, data: BaseFormatter):
        """This function is called by the YAML dumper to convert a
        :class:`Formatter` object into a YAML node.

        It should not be called directly.
        """
        data = {
            "class": type(data),
            "state": data._get_state(),
        }
        return dumper.represent_mapping("!Formatter", data)

    @staticmethod
    def from_yaml(loader, node):
        """This function is called by the YAML loader to convert a YAML node
        into an :class:`Formatter` object.

        It should not be called directly.
        """
        data = loader.construct_mapping(node, deep=True)
        formatter = data["class"].__new__(data["class"])
        formatter._set_state(data["state"])
        return formatter

    def html(self, cell: Any):
        """When not in interactive mode, objects are visualized using static
        html.

        This method should produce that static html for the cell.
        """
        return str(cell)


class Formatter(BaseFormatter):
    # TODO: set the signature of the __init__ so it works with autocomplete and docs
    def __init__(self, **kwargs):
        for k in kwargs:
            if k not in self.component_class.prop_names():
                raise ValueError(f"{k} is not a valid prop for {self.component_class}")

        for prop_name, field in self.component_class.model_fields.items():
            if prop_name != self.data_prop and prop_name not in kwargs:
                if field.is_required():
                    raise ValueError("""Missing required argument.""")
                kwargs[prop_name] = field.default
        self._props = kwargs

    def encode(self, cell: str):
        return cell

    @property
    def props(self) -> Dict[str, Any]:
        return self._props

    def _get_state(self) -> Dict[str, Any]:
        return {
            "_props": self._props,
        }

    def _set_state(self, state: Dict[str, Any]):
        self._props = state["_props"]


MeerkatDumper.add_multi_representer(BaseFormatter, BaseFormatter.to_yaml)
MeerkatLoader.add_constructor("!Formatter", BaseFormatter.from_yaml)


class DeferredFormatter(BaseFormatter):
    def __init__(self, formatter: BaseFormatter):
        self.wrapped = formatter

    def encode(self, cell: DeferredCell, **kwargs):
        if self.wrapped.static_encode:
            return self.wrapped.encode(None, **kwargs)
        return self.wrapped.encode(cell(), **kwargs)

    @property
    def component_class(self):
        return self.wrapped.component_class

    @property
    def data_prop(self):
        return self.wrapped.data_prop

    @property
    def props(self):
        return self.wrapped.props

    def html(self, cell: DeferredCell):
        return self.wrapped.html(cell())

    def _get_state(self):
        data = {
            "wrapped": {
                "class": self.wrapped.__class__,
                "state": self.wrapped._get_state(),
            },
        }
        return data

    def _set_state(self, state: Dict[str, Any]):
        wrapped_state = state["wrapped"]
        wrapped = wrapped_state["class"].__new__(wrapped_state["class"])
        wrapped._set_state(wrapped_state["state"])
        self.wrapped = wrapped


MeerkatDumper.add_multi_representer(DeferredFormatter, DeferredFormatter.to_yaml)
MeerkatLoader.add_constructor("!DeferredFormatter", DeferredFormatter.from_yaml)
