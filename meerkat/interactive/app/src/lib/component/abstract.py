import collections
import inspect
import os
import typing
import uuid
import warnings
from typing import Dict, List, Set

from pydantic import BaseModel, ConfigDict, Extra, root_validator, model_validator

from meerkat.constants import MEERKAT_NPM_PACKAGE, PathHelper
from meerkat.dataframe import DataFrame
from meerkat.interactive.endpoint import Endpoint, EndpointProperty
from meerkat.interactive.event import EventInterface
from meerkat.interactive.frontend import FrontendMixin
from meerkat.interactive.graph import Store
from meerkat.interactive.node import Node, NodeMixin
from meerkat.mixins.identifiable import IdentifiableMixin
from meerkat.tools.utils import (
    classproperty,
    get_type_hint_args,
    get_type_hint_origin,
    has_var_kwargs,
    is_subclass,
    nested_apply,
)

try:
    collections_abc = collections.abc
except AttributeError:
    collections_abc = collections

try:
    from typing import Literal
except ImportError:
    from typing_extensions import Literal


class ComponentFrontend(BaseModel):
    name: str
    props: Dict
    slots: list


class WrappableMixin:
    @classproperty
    def wrapper_import_style(cls) -> Literal["default", "named", "none"]:
        # TODO: this will create issues if users want to use plotly components
        # in mk init apps. In general, we need to make the library / namespace
        # distinction more explicit and this system more robust.
        if cls.library == MEERKAT_NPM_PACKAGE and (
            cls.namespace == "meerkat" or cls.namespace == "plotly"
        ):
            # Meerkat components
            if not PathHelper().is_user_app:
                # In Meerkat package
                # Use named import: import Something from "path/to/component";
                return "named"
            else:
                # Use default import: import { Something } from MEERKAT_NPM_PACKAGE;
                return "default"
        elif cls.library == MEERKAT_NPM_PACKAGE:
            # Custom user components
            if PathHelper().is_user_app:
                # Use named import: import Something from "path/to/component";
                return "named"
            else:
                # This should never happen: we should never be wrapping a custom
                # component directly in the Meerkat package + no components
                # in Meerkat should have a namespace other than "meerkat"
                raise ValueError(
                    f"Cannot use custom component {cls.component_name}, "
                    "please initialize a Meerkat app using `mk init` first."
                )
        elif cls.library == "html":
            # No need to import HTML tags
            return "none"
        else:
            return "default"


class PythonToSvelteMixin:
    def get_components(self) -> Set[str]:
        nested_components = set()
        nested_components.add(self.component_name)
        for s in self.slots:
            nested_components.update(s.get_components())
        if hasattr(self, "component"):
            nested_components.update(self.component.get_components())
        if hasattr(self, "components"):
            for c in self.components:
                nested_components.update(c.get_components())
        return nested_components


class Slottable:
    @classproperty
    def slottable(cls) -> bool:
        return True


def iterable(arg):
    return isinstance(arg, collections_abc.Iterable) and not isinstance(arg, str)


class SlotsMixin:
    def __init__(self, slots: List["BaseComponent"] = [], *args, **kwargs):
        super().__init__(*args, **kwargs)

        if isinstance(slots, BaseComponent) or not iterable(slots):
            slots = [slots]
        self._slots = slots

    @property
    def slots(self) -> List["BaseComponent"]:
        from meerkat.interactive.app.src.lib.component.core.put import Put

        _slots = []
        for slot in self._slots:
            if not isinstance(slot, BaseComponent):
                # Wrap it in a Put component
                _slots.append(Put(data=slot))
            else:
                _slots.append(slot)
        return _slots

    def append(self, other):
        # Allow users to append to slots
        from meerkat.interactive.app.src.lib.component.core.put import Put

        if isinstance(other, BaseComponent):
            self._slots.append(other)
        else:
            self._slots.append(Put(data=other))

    @classproperty
    def slottable(cls) -> bool:
        return False


class BaseComponent(
    IdentifiableMixin,
    FrontendMixin,
    SlotsMixin,
    WrappableMixin,
    PythonToSvelteMixin,
    BaseModel,
):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="allow",
        copy_on_model_validation="none"
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def __getattribute__(self, name):
        if name == "component_id":
            # need to wrap in a Store so component_id is passed through the wrapper
            return Store(self.id)

        value = super().__getattribute__(name)

        if isinstance(value, Node):
            # because the validator converts dataframes to nodes, when the
            # dataframe is accessed we need to convert it back to the dataframe
            return value.obj
        return value

    @classproperty
    def alias(cls):
        """Unique alias for this component that uses the namespace and the name
        of the BaseComponent subclass.

        This will give components with the same name from different
        libraries different names e.g. `MeerkatButton` and
        `CarbonButton`.
        """
        return cls.namespace.title() + cls.__name__

    @classproperty
    def frontend_alias(cls):
        """Alias for this component that is used in the frontend.

        This is not unique, and it is possible to have multiple
        components with the same frontend alias. This is useful for
        components that are just wrappers around other components, e.g.
        a layout BaseComponent that subclasses a Grid BaseComponent will
        still have the same frontend alias as the Grid BaseComponent.
        """
        return cls.namespace.title() + cls.component_name

    @classproperty
    def component_name(cls):
        # Inheriting an existing BaseComponent and modifying it on the Python side
        # should not change the name of the component used on the frontend
        if cls.__bases__[0] != BaseComponent and issubclass(
            cls.__bases__[0], BaseComponent
        ):
            return cls.__bases__[0].__name__

        return cls.__name__

    @classproperty
    def event_names(cls) -> List[str]:
        """Returns a list of event names that this component emits."""
        return [
            k[3:]
            for k in cls.__fields__
            if k.startswith("on_")
            and not issubclass(cls.__fields__[k].type_, EndpointProperty)
        ]

    @classproperty
    def events(cls) -> List[str]:
        """Returns a list of events that this component emits."""
        return [
            k
            for k in cls.__fields__
            if k.startswith("on_")
            and not issubclass(cls.__fields__[k].type_, EndpointProperty)
        ]

    @classproperty
    def identifiable_group(self):
        # Ordinarily, we would create a new classproperty for this, like
        # _self_identifiable_group: str = "components"
        # However, this causes pydantic to show _self_identifiable_group in
        # type hints when using the component in the IDE, which might
        # be confusing to users.
        # We just override the classproperty here directly as an alternative.
        return "components"

    @classproperty
    def library(cls):
        return MEERKAT_NPM_PACKAGE

    @classproperty
    def namespace(cls):
        return "meerkat"

    @classproperty
    def path(cls):
        if not cls.library == MEERKAT_NPM_PACKAGE or (
            cls.library == MEERKAT_NPM_PACKAGE
            # KG: TODO: Temporary hack to be able to use multiple namespaces
            # for components provided natively in the Meerkat library.
            and (cls.namespace == "meerkat" or cls.namespace == "plotly")
            and PathHelper().is_user_app
        ):
            return cls.library

        path = os.path.join(
            os.path.dirname(inspect.getfile(cls)),
            f"{cls.component_name}.svelte",
        )
        if os.path.exists(path):
            return path

        # Raise an error if the file doesn't exist
        raise FileNotFoundError(
            f"Could not find {path}. "
            f"Check that the definition of this BaseComponent {cls} "
            "is in the same folder as the Svelte file. "
            "You might also be using a "
            "component from a library, in which case set the `library` "
            "property of the BaseComponent correctly."
        )

    @classproperty
    def prop_names(cls):
        return [
            k for k in cls.__fields__ if not k.startswith("on_") and "_self_id" != k
        ] + [
            k
            for k in cls.__fields__
            if k.startswith("on_")
            and issubclass(cls.__fields__[k].type_, EndpointProperty)
        ]

    @classproperty
    def prop_bindings(cls):
        if not issubclass(cls, Component):
            # These props need to be bound with `bind:` in Svelte
            types_to_bind = {Store, DataFrame}
            return {
                prop: cls.__fields__[prop].type_ in types_to_bind
                for prop in cls.prop_names
            }
        else:
            return {
                prop: (cls.__fields__[prop].type_ != EndpointProperty)
                for prop in cls.prop_names
            }

    @property
    def frontend(self):
        def _frontend(value):
            if isinstance(value, FrontendMixin):
                return value.frontend
            return value

        frontend_props = nested_apply(
            self.virtual_props,
            _frontend,
            base_types=(Store),
        )
        return ComponentFrontend(
            # component_id=self.id,
            # path=os.path.join(
            #     os.path.dirname(inspect.getfile(self.__class__)),
            #     f"{self.component_name}.svelte",
            # ),
            # name=self.alias,
            name=self.frontend_alias,
            props=frontend_props,
            slots=[slot.frontend for slot in self.slots],
            # library=self.library,
        )

    @property
    def props(self):
        return {k: self.__getattribute__(k) for k in self.prop_names}

    @property
    def virtual_props(self):
        """Props, and all events (as_*) as props."""
        vprop_names = [k for k in self.__fields__ if "_self_id" != k] + ["component_id"]
        return {k: self.__getattribute__(k) for k in vprop_names}

    @model_validator(mode="before")
    def _init_cache(cls, values):
        # This is a workaround because Pydantic automatically converts
        # all Store objects to their underlying values when validating
        # the class. We need to keep the Store objects around.
        cls._cache = values.copy()
        return values

    @model_validator(mode="before")
    def _endpoint_name_starts_with_on(cls, values):
        """Make sure that all `Endpoint` fields have a name that starts with
        `on_`."""
        # TODO: this shouldn't really be a validator, this needs to be run
        # exactly once when the class is created.

        # Iterate over all fields in the class
        for k, v in cls.__fields__.items():
            # TODO: revisit this. Here we only enforce the on_* naming convention for
            # endpoints, not endpoint properties, but this should be reconsidered.
            if is_subclass(v.type_, Endpoint) and not is_subclass(
                v.type_, EndpointProperty
            ):
                if not k.startswith("on_"):
                    raise ValueError(
                        f"Endpoint {k} must have a name that starts with `on_`"
                    )
        return values

    @staticmethod
    def _get_event_interface_from_typehint(type_hint):
        """Recurse on type hints to find all the Endpoint[EventInterface]
        types.

        Only run this on the type hints of a Component, for fields that are
        endpoints.

        Returns:
            EventInterface: The EventInterface that the endpoint expects. None if
                the endpoint does not have a type hint for the EventInterface.
        """
        if isinstance(type_hint, typing._GenericAlias):
            origin = get_type_hint_origin(type_hint)
            args = get_type_hint_args(type_hint)

            if is_subclass(origin, Endpoint):
                # Endpoint[XXX]
                if len(args) != 1:
                    raise TypeError(
                        "Endpoint type hints should only have one EventInterface."
                    )
                if not issubclass(args[0], EventInterface):
                    raise TypeError(
                        "Endpoint type hints should be of type EventInterface."
                    )
                return args[0]
            else:
                # Alias[XXX]
                for arg in args:
                    out = BaseComponent._get_event_interface_from_typehint(arg)
                    if out is not None:
                        return out
        return None

    @model_validator(mode="before")
    def _endpoint_signature_matches(cls, values):
        """Make sure that the signature of the Endpoint that is passed in
        matches the parameter names and types that are sent from Svelte.

        Procedurally, this validator:
            - Gets the type hints for this BaseComponent subclass.
            - Gets all fields that are endpoints.
            - Gets the EventInterface from the Endpoint type hint.
            - Gets the parameters from the EventInterface.
            - Gets the function passed by the user.
            - Gets the parameters from the function.
            - Compares the two sets of parameters.
        """

        type_hints = typing.get_type_hints(cls)

        # Get all fields that pydantic tells us are endpoints.
        for field, value in cls.__fields__.items():
            if (
                not is_subclass(value.type_, Endpoint)
                or field not in values
                or values[field] is None
            ):
                continue

            # Pull out the EventInterface from Endpoint.
            event_interface = cls._get_event_interface_from_typehint(type_hints[field])
            if event_interface is None:
                warnings.warn(
                    f"Endpoint `{field}` does not have a type hint. "
                    "We recommend subclassing EventInterface to provide "
                    "an explicit type hint to users."
                )
                continue

            # Get the parameters from the EventInterface.
            event_interface_params = typing.get_type_hints(event_interface).keys()

            # Get the endpoint passed by the user.
            endpoint = values[field]
            # Raise an error if it's not an Endpoint.
            if not isinstance(endpoint, Endpoint):
                raise TypeError(
                    f"Endpoint `{field}` should be of type Endpoint, "
                    f"but is of type {type(endpoint)}."
                )

            fn = endpoint.fn
            fn_signature = inspect.signature(fn)
            fn_params = fn_signature.parameters.keys()

            # Make sure that the parameters passed by the user are a superset of
            # the parameters expected by the EventInterface.
            # NOTE: if the function has a ** argument, which will absorb any extra
            # parameters passed by the Svelte dispatch call. So we do not need to
            # do the superset check.
            remaining_params = event_interface_params - fn_params
            if not has_var_kwargs(fn) and len(remaining_params) > 0:
                raise TypeError(
                    f"Endpoint `{field}` will be called with parameters: "
                    f"{', '.join(f'`{param}`' for param in event_interface_params)}. "
                    "\n"
                    f"Function specified by the user is missing the "
                    "following parameters: "
                    f"{', '.join(f'`{param}`' for param in remaining_params)}. "
                )

            # Check that the frontend will provide all of the necessary arguments
            # to call fn. i.e. fn should not have any remaining args once the
            # frontend sends over the inputs.
            # Do this by making a set of all fn parameters that don't have defaults.
            # This set should be a subset of the EventInterface.parameters.

            # Get all the parameters that don't have default values
            required_fn_params = {
                k: v
                for k, v in fn_signature.parameters.items()
                if v.default is v.empty
                and v.kind not in (v.VAR_POSITIONAL, v.VAR_KEYWORD)
            }

            # Make sure that the EventInterface parameters are a super set of these
            # required parameters.
            if not set(required_fn_params).issubset(set(event_interface_params)):
                raise TypeError(
                    f"Endpoint `{field}` will be called with parameters: "
                    f"{', '.join(f'`{param}`' for param in event_interface_params)}. "
                    f"Check the {event_interface.__name__} class to see what "
                    "parameters are expected to be passed in."
                    "\n"
                    f"The function `{fn}` expects the following parameters: "
                    f"{', '.join(f'`{param}`' for param in required_fn_params)}. "
                    f"Perhaps you forgot to fill out all of the parameters of {fn}?"
                )

        return values

    @model_validator(mode="before")
    def _update_cache(cls, values):
        # `cls._cache` only contains the values that were passed in
        # `values` contains all the values, including the ones that
        # were not passed in

        # Users might run validators on the class, which will
        # update the `values` dict. We need to make sure that
        # the values in `cls._cache` are updated as well.
        for k, v in cls._cache.items():
            if k in values:
                if isinstance(v, Store):
                    v.set(values[k])
                else:
                    cls._cache[k] = values[k]
                # TODO: other types of objects that need to be updated
            else:
                # This has happened with a parameter that
                # - had no default value
                # - was annotated without `Optional[...]`
                # - was passed in as a `None` value
                # TODO: There may be other cases where this happens.
                pass
        return values

    @model_validator(mode="before")
    def _check_inode(cls, values):
        """Unwrap NodeMixin objects to their underlying Node (except
        Stores)."""
        values.update(cls._cache)
        for name, value in values.items():
            if isinstance(value, NodeMixin) and not isinstance(value, Store):
                # Now value is a NodeMixin object
                # We need to make sure that value points to a Node in the graph
                # If it doesn't, we need to add it to the graph
                if not value.has_inode():
                    value.attach_to_inode(value.create_inode())

                # Now value is a NodeMixin object that points to a Node in the graph

                # We replace `value` with `value.inode`, and will send
                # this to the frontend
                # Effectively, NodeMixin objects (except Store) are "by reference"
                # and not "by value" (this is also why we explicitly exclude
                # Store from this check, which is "by value")
                values[name] = value.inode
            else:
                values[name] = value
        cls._cache = values
        return values

    def _get_ipython_height(self) -> str:
        """Return the height of the viewport used to render this component in
        the notebook. Value will be pased to IPython.display.IFrame as the
        height argument.

        TODO: Figure out how to do this dynamically.
        """
        return "100%"

    def _ipython_display_(self):
        from IPython.display import display

        from meerkat.interactive.page import Page

        display(
            Page(
                component=self,
                id=self.__class__.__name__ + str(uuid.uuid4()),
                height=self._get_ipython_height(),
                progress=False,
            ).launch()
        )

    # class Config:
    #     arbitrary_types_allowed = True
    #     extra = Extra.allow
    #     copy_on_model_validation = False


class Component(BaseComponent):
    """Component with simple defaults."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="allow",
        ignored_types=(Endpoint, EndpointProperty),
    )

    @classproperty
    def component_name(cls):
        # Inheriting an existing Component and modifying it on the Python side
        # should not change the name of the component used on the frontend
        if cls.__bases__[0] != Component and issubclass(cls.__bases__[0], Component):
            return cls.__bases__[0].component_name

        return cls.__name__

    @model_validator(mode="before")
    def _init_cache(cls, values):
        # This is a workaround because Pydantic automatically converts
        # all Store objects to their underlying values when validating
        # the class. We need to keep the Store objects around.

        # Cache all the Store objects
        cls._cache = values.copy()

        # Convert all the Store objects to their underlying values
        # and return the unwrapped values
        for name, value in values.items():
            if isinstance(value, Store):
                values[name] = value.__wrapped__
            else:
                values[name] = value

        return values

    @model_validator(mode="before")
    def _convert_fields(cls, values: dict):
        values = cls._cache
        cls._cache = None
        for name, value in values.items():
            # Wrap all the fields that are not NodeMixins in a Store
            # (i.e. this will exclude DataFrame, Endpoint etc. as well as
            # fields that are already Stores)
            if (
                name not in cls.__fields__
                or cls.__fields__[name].type_ == Endpoint
                or cls.__fields__[name].type_ == EndpointProperty
            ):
                # Separately skip Endpoint fields by looking at the field type,
                # since they are assigned None by default and would be missed
                # by the condition below
                continue

            if not isinstance(value, NodeMixin) and not isinstance(value, Node):
                value = values[name] = Store(value)

            # Now make sure that all the `Store` objects have inodes
            if hasattr(value, "has_inode") and not value.has_inode():
                value.attach_to_inode(value.create_inode())

        return values
