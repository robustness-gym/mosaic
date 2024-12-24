from __future__ import annotations

import inspect
import logging
import typing
from functools import partial, wraps
from typing import Any, Callable, Generic, Optional, Union

from fastapi import APIRouter, Body
from pydantic import BaseModel, create_model

from meerkat.interactive.graph import Store, trigger, unmarked
from meerkat.interactive.graph.store import _unpack_stores_from_object
from meerkat.interactive.node import Node, NodeMixin
from meerkat.interactive.types import T
from meerkat.mixins.identifiable import IdentifiableMixin, is_meerkat_id
from meerkat.state import state
from meerkat.tools.utils import get_type_hint_args, get_type_hint_origin, has_var_args

logger = logging.getLogger(__name__)

# KG: must declare this dynamically defined model here,
# otherwise we get a FastAPI error
# when only declaring this inside the Endpoint class.
FnPydanticModel = None


class SingletonRouter(type):
    """A metaclass that ensures that only one instance of a router is created,

    *for a given prefix*.

    A prefix is a string that is used to identify a router. For example,
    the prefix for the router that handles endpoints is "/endpoint". We
    want to ensure that only one router is created for each prefix.
    """

    _instances = {}

    def __call__(cls, *args, **kwargs):
        prefix = kwargs["prefix"]
        # Look up if this (cls, prefix) pair has been created before
        if (cls, prefix) not in cls._instances:
            # If not, we let a new instance be created
            cls._instances[(cls, prefix)] = super(SingletonRouter, cls).__call__(
                *args, **kwargs
            )
        return cls._instances[(cls, prefix)]


class SimpleRouter(IdentifiableMixin, APIRouter):  # , metaclass=SingletonRouter):
    # KG: using the SingletonRouter metaclass causes a bug.
    # app.include_router() inside Endpoint is called multiple times
    # for the same router. This causes an error because some
    # endpoints are registered multiple times because the FastAPI
    # class doesn't check if an endpoint is already registered.
    # As a patch, we're generating one router per Endpoint object
    # (this could generate multiple routers for the same prefix, but
    # that's not been a problem).
    """A very simple FastAPI router.

    This router allows you to pass in arbitrary keyword arguments that are
    passed to the FastAPI router, and sets sensible defaults for the
    prefix, tags, and responses.

    Note that if you create two routers with the same prefix, they will
    not be the same object.

    Attributes:
        prefix (str): The prefix for this router.
        **kwargs: Arbitrary keyword arguments that are passed to the FastAPI
            router.
    """

    _self_identifiable_group: str = "routers"

    def __init__(self, prefix: str, **kwargs):
        super().__init__(
            prefix=prefix,
            tags=[prefix.strip("/").replace("/", "-")],
            responses={404: {"description": "Not found"}},
            id=self.prepend_meerkat_id_prefix(prefix),
            **kwargs,
        )


class EndpointFrontend(BaseModel):
    """A schema for sending an endpoint to the frontend."""

    endpointId: Union[str, None]


# TODO: technically Endpoint doesn't need to be NodeMixin (probably)
class Endpoint(IdentifiableMixin, NodeMixin, Generic[T]):
    EmbeddedBody = partial(Body, embed=True)
    _self_identifiable_group: str = "endpoints"

    def __init__(
        self,
        fn: Callable = None,
        prefix: Union[str, APIRouter] = None,
        route: str = None,
    ):
        """Create an endpoint from a function in Meerkat.

        Typically, you will not need to call this class directly, but
        instead use the `endpoint` decorator.

        Attributes:
            fn (Callable): The function to create an endpoint from.
            prefix (str): The prefix for this endpoint.
            route (str): The route for this endpoint.

        Note:
        All endpoints can be hit with a POST request at
        /{endpoint_id}/dispatch/
        The request needs a JSON body with the following keys:
            - kwargs: a dictionary of keyword arguments to be
                passed to the endpoint function `fn`
            - payload: additional payload, if any

        Optionally, the user can customize how endpoints are
        organized by specifying a prefix and a route. The prefix
        is a string that is used to identify a router. For example,
        the prefix for the router that handles endpoints is "/endpoint".
        The route is a string that is used to identify an endpoint
        within a router. For example, the route for the endpoint
        that handles the `get` function could be "/get".

        If only a prefix is specified, then the route will be the
        name of the function e.g. "my_endpoint". If both a prefix
        and a route are specified, then the route will be the
        specified route e.g. "/specific/route/".

        Refer to the FastAPI documentation for more information
        on how to create routers and endpoints.
        """
        super().__init__()
        if fn is None:
            self.id = None
        self.fn = fn
        self._validate_fn()

        if prefix is None:
            # No prefix, no router
            self.router = None
        else:
            # Make the router
            if isinstance(prefix, APIRouter):
                self.router = prefix
            else:
                self.router = SimpleRouter(prefix=prefix)

        self.prefix = prefix
        self.route = route

    def __repr__(self) -> str:
        if hasattr(self.fn, "__name__"):
            name = self.fn.__name__
        elif hasattr(self.fn, "func"):
            name = self.fn.func.__name__
        else:
            name = None
        return (
            f"Endpoint(id={self.id}, name={name}, prefix={self.prefix}, "
            f"route={self.route})"
        )

    def _validate_fn(self):
        """Validate the function `fn`."""
        if not callable(self.fn):
            raise TypeError(f"Endpoint function {self.fn} is not callable.")

        # Disallow *args
        if has_var_args(self.fn):
            raise TypeError(
                f"Endpoint function {self.fn} has a `*args` parameter."
                " Please use keyword arguments instead."
            )

        # Do we allow lambdas?

    @property
    def frontend(self):
        return EndpointFrontend(
            endpointId=self.id,
        )

    def to_json(self):
        return {"endpointId": self._self_id}

    def run(self, *args, **kwargs) -> Any:
        """Actually run the endpoint function `fn`.

        Args:
            *args: Positional arguments to pass to `fn`.
            **kwargs: Keyword arguments to pass to `fn`.

        Returns:
            The return value of `fn`.
        """
        logger.debug(f"Running endpoint {self}.")

        # Apply a partial function to ingest the additional arguments
        # that are passed in
        partial_fn = partial(self.fn, *args, **kwargs)

        # Check if the partial_fn has any arguments left to be filled
        spec = inspect.getfullargspec(partial_fn)
        # Check if spec has no args: if it does have args,
        # it means that we can't call the function without filling them in
        no_args = len(spec.args) == 0
        # Check if all the kwonlyargs are in the keywords: if yes, we've
        # bound all the keyword arguments
        no_kwonlyargs = all([arg in partial_fn.keywords for arg in spec.kwonlyargs])

        # Get the signature
        signature = inspect.signature(partial_fn)
        # Check if any parameters are unfilled args
        no_unfilled_args = all(
            [
                param.default is not param.empty
                for param in signature.parameters.values()
            ]
        )

        if not (no_args and no_kwonlyargs and no_unfilled_args):
            # Find the missing keyword arguments
            missing_args = [
                arg for arg in spec.kwonlyargs if arg not in partial_fn.keywords
            ] + [
                param.name
                for param in signature.parameters.values()
                if param.default == param.empty
            ]
            raise ValueError(
                f"Endpoint {self.id} still has arguments left to be \
                filled (args: {spec.args}, kwargs: {missing_args}). \
                    Ensure that all keyword arguments \
                    are passed in when calling `.run()` on this endpoint."
            )

        # Clear the modification queue before running the function
        # This is an invariant: there should be no pending modifications
        # when running an endpoint, so that only the modifications
        # that are made by the endpoint are applied
        state.modification_queue.clear()

        # Ready the ModificationQueue so that it can be used to track
        # modifications made by the endpoint
        state.modification_queue.ready()
        state.progress_queue.add(
            self.fn.func.__name__ if isinstance(self.fn, partial) else self.fn.__name__
        )

        try:
            # The function should not add any operations to the graph.
            with unmarked():
                result = partial_fn()
        except Exception as e:
            # Unready the modification queue
            state.modification_queue.unready()
            raise e

        with unmarked():
            modifications = trigger()

        # End the progress bar
        state.progress_queue.add(None)

        return result, modifications

    def partial(self, *args, **kwargs) -> Endpoint:
        # Any NodeMixin objects that are passed in as arguments
        # should have this Endpoint as a non-triggering child
        if not self.has_inode():
            node = self.create_inode()
            self.attach_to_inode(node)

        for arg in list(args) + list(kwargs.values()):
            if isinstance(arg, NodeMixin):
                if not arg.has_inode():
                    inode_id = None if not isinstance(arg, Store) else arg.id
                    node = arg.create_inode(inode_id=inode_id)
                    arg.attach_to_inode(node)

                arg.inode.add_child(self.inode, triggers=False)

        # TODO (sabri): make this work for derived dataframes
        # There's a subtle issue with partial that we should figure out. I spent an
        # hour or so on it, but am gonna table it til after the deadline tomorrow
        # because I have a hacky workaround. Basically, if we create an endpoint
        # partial passing a "derived" dataframe, when the endpoint is called, we
        # should expect that the current value of the dataframe will be passed.
        # Currently, the original value of the dataframe is passed. It makes sense to
        # me why this is happening, but the right fix is eluding me.

        # All NodeMixin objects need to be replaced by their node id.
        # This ensures that we can resolve the correct object at runtime
        # even if the object is a result of a reactive function
        # (i.e. not a root of the graph).
        def _get_node_id_or_arg(arg):
            if isinstance(arg, NodeMixin):
                assert arg.has_inode()
                return arg.inode.id
            return arg

        args = [_get_node_id_or_arg(arg) for arg in args]
        kwargs = {key: _get_node_id_or_arg(val) for key, val in kwargs.items()}

        fn = partial(self.fn, *args, **kwargs)
        fn.__name__ = self.fn.__name__
        return Endpoint(
            fn=fn,
            prefix=None,
            route=None,
        )

    def compose(self, fn: Union[Endpoint, Callable]) -> Endpoint:
        """Create a new Endpoint that applies `fn` to the return value of this
        Endpoint. Effectively equivalent to `fn(self.fn(*args, **kwargs))`.

        If the return value is None and `fn` doesn't take any inputs, then
        `fn` will be called with no arguments.

        Args:
            fn (Endpoint, callable): An Endpoint or a callable function that accepts
                a single argument of the same type as the return of this Endpoint
                (i.e. self).

        Return:
            Endpoint: The new composed Endpoint.
        """
        if not isinstance(fn, Endpoint):
            fn = Endpoint(fn=fn)

        # `fn` may not take any inputs.
        # FIXME: Should this logic be in ``compose``? or some other function?
        sig = get_signature(fn)
        pipe_return = len(sig.parameters) > 0

        @wraps(self.fn)
        def composed(*args, **kwargs):
            out = self.fn(*args, **kwargs)
            return fn.fn(out) if pipe_return else fn.fn()

        composed.__name__ = f"composed({str(self)} | {str(fn)})"

        return Endpoint(
            fn=composed,
            prefix=self.prefix,
            route=self.route,
        )

    def add_route(self, method: str = "POST") -> None:
        """Add a FastAPI route for this endpoint to the router. This function
        will not do anything if the router is None (i.e. no prefix was
        specified).

        This function is called automatically when the endpoint is
        created using the `endpoint` decorator.
        """
        if self.router is None:
            return

        if self.route is None:
            # The route will be postfixed with the fn name
            self.route = f"/{self.fn.__name__}/"

            # Analyze the function signature of `fn` to
            # construct a dictionary, mapping argument names
            # to their types and default values for creating a
            # Pydantic model.

            # During this we also
            # - make sure that args are either type-hinted or
            #   annotated with a default value (can't create
            #  a Pydantic model without a type hint or default)
            # - replace arguments that have type-hints which
            #   are subclasses of `IdentifiableMixin` with
            #   strings (i.e. the id of the Identifiable)
            #   (e.g. `Store` -> `str`)
            signature = inspect.signature(self.fn)

            pydantic_model_params = {}
            for p in signature.parameters:
                annot = signature.parameters[p].annotation
                default = signature.parameters[p].default
                has_default = default is not inspect._empty

                if annot is inspect.Parameter.empty:
                    if p == "kwargs":
                        # Allow arbitrary keyword arguments
                        pydantic_model_params[p] = (dict, ...)
                        continue

                    if not has_default:
                        raise ValueError(
                            f"Parameter {p} must have a type annotation or "
                            "a default value."
                        )
                elif isinstance(annot, type) and issubclass(annot, IdentifiableMixin):
                    # e.g. Stores must be referred to by str ids when
                    # passed into the API
                    pydantic_model_params[p] = (str, ...)
                else:
                    pydantic_model_params[p] = (
                        (annot, default) if has_default else (annot, ...)
                    )

            # Allow arbitrary types in the Pydantic model
            class Config:
                arbitrary_types_allowed = True

            # Create the Pydantic model, named `{fn_name}Model`
            global FnPydanticModel
            FnPydanticModel = create_model(
                f"{self.fn.__name__.capitalize()}{self.prefix.replace('/', '').capitalize()}Model",  # noqa: E501
                __config__=Config,
                **pydantic_model_params,
            )

            # Create a wrapper function, with kwargs that conform to the
            # Pydantic model, and a return annotation that matches `fn`
            def _fn(
                kwargs: FnPydanticModel = Endpoint.EmbeddedBody(),
            ):  # -> signature.return_annotation:
                return self.fn(**kwargs.dict())

            # from inspect import Parameter, Signature
            # params = []
            # for p, (annot, default) in pydantic_model_params.items():
            #     params.append(
            #         Parameter(
            #             p,
            #             kind=Parameter.POSITIONAL_OR_KEYWORD,
            #             annotation=annot,
            #             default=default,
            #         )
            #     )
            # _fn.__signature__ = Signature(params)

            # Name the wrapper function the same as `fn`, so it looks nice
            # in the docs
            _fn.__name__ = self.fn.__name__
        else:
            # If the user specifies a route manually, then they're responsible for
            # everything, including type-hints and default values.
            signature = inspect.signature(self.fn)
            for p in signature.parameters:
                annot = signature.parameters[p].annotation

                # If annot is a subclass of `IdentifiableMixin`, replace
                # it with the `str` type (i.e. the id of the Identifiable)
                # (e.g. `Store` -> `str`)
                if isinstance(annot, type) and issubclass(annot, IdentifiableMixin):
                    self.fn.__annotations__[p] = str

            _fn = self.fn

        # Make FastAPI endpoint for POST requests
        self.router.add_api_route(
            self.route + "/" if not self.route.endswith("/") else self.route,
            _fn,
            methods=[method],
        )

        # Must add the router to the app again, everytime a new route is added
        # otherwise, the new route does not show up in the docs
        from meerkat.interactive.api.main import app

        app.include_router(self.router)

    def __call__(self, *args, __fn_only=False, **kwargs):
        """Calling the endpoint will just call .run(...) by default.

        If `__fn_only=True` is specified, it will call the raw function
        underlying this endpoint.
        """
        if __fn_only:
            # FIXME(Sabri): This isn't working for some reason. The '__fn_only' arg
            # is for some reason being put in the kwargs dict. Workaround is to just
            # use self.fn directly.
            return self.fn(*args, **kwargs)
        return self.run(*args, **kwargs)

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not isinstance(v, cls):
            return make_endpoint(v)
        return v


class EndpointProperty(Endpoint, Generic[T]):
    @classmethod
    def is_endpoint_property(cls, type_hint):
        """Check if a type hint is an EndpointProperty or a Union of EndpointProperties."""
        if isinstance(type_hint, type) and issubclass(type_hint, EndpointProperty):
            return True

        if isinstance(type_hint, typing._GenericAlias):
            origin = get_type_hint_origin(type_hint)
            args = get_type_hint_args(type_hint)

            if origin == typing.Union:
                return any(cls.is_endpoint_property(arg) for arg in args)
            elif isinstance(origin, type):
                return issubclass(origin, EndpointProperty)

        return False


def make_endpoint(endpoint_or_fn: Union[Callable, Endpoint, None]) -> Endpoint:
    """Make an Endpoint."""
    return (
        endpoint_or_fn
        if isinstance(endpoint_or_fn, Endpoint)
        else Endpoint(endpoint_or_fn)
    )


def endpoint(
    fn: Optional[Callable] = None,
    prefix: Optional[Union[str, APIRouter]] = None,
    route: Optional[str] = None,
    method: str = "POST",
) -> Endpoint:
    """Decorator to mark a function as an endpoint.

    An endpoint is a function that can be called to
        - update the value of a Store (e.g. incrementing a counter)
        - update a DataFrame (e.g. adding a new row)
        - run a computation and return its result to the frontend
        - run a function in response to a frontend event (e.g. button
            click)

    Endpoints differ from reactive functions in that they are not
    automatically triggered by changes in their inputs. Instead,
    they are triggered by explicit calls to the endpoint function.

    The Store and DataFrame objects that are modified inside the endpoint
    function will automatically trigger reactive functions that
    depend on them.

    .. code-block:: python

        @endpoint
        def increment(count: Store, step: int = 1):
            count.set(count + step)
            # ^ update the count Store, which will trigger operations
            #   that depend on it

        # Create a button that calls the increment endpoint
        counter = Store(0)
        button = Button(on_click=increment(counter))
        # ^ read this as: call the increment endpoint with the `counter`
        # Store when the button is clicked

    Args:
        fn: The function to decorate.
        prefix: The prefix to add to the route. If a string, it will be
            prepended to the route. If an APIRouter, the route will be
            added to the router.
        route: The route to add to the endpoint. If not specified, the
            route will be the name of the function.
        method: The HTTP method to use for the endpoint. Defaults to
            "POST".

    Returns:
        The decorated function, as an Endpoint object.
    """
    if fn is None:
        return partial(endpoint, prefix=prefix, route=route, method=method)

    @wraps(fn)
    def _endpoint(fn: Callable):
        # Gather up
        # 1. all the arguments that are hinted as Stores
        # 2. the hinted arguments that subclass IdentifiableMixin
        #    e.g. Store, Endpoint, Page, etc.
        stores = set()
        identifiables = {}
        for name, annot in inspect.getfullargspec(fn).annotations.items():
            is_annotation_store = _is_annotation_store(annot)
            if is_annotation_store:
                stores.add(name)

            # TODO: See if we can remove this in the future.
            if is_annotation_store or (
                isinstance(annot, type) and issubclass(annot, IdentifiableMixin)
            ):
                # This will also include `Store`, so it will be a superset
                # of `stores`
                identifiables[name] = annot

        @wraps(fn)
        def wrapper(*args, **kwargs):
            # Keep the arguments that were not annotated to be `Stores`
            fn_signature = inspect.signature(fn)
            fn_bound_arguments = fn_signature.bind(*args, **kwargs).arguments

            # `Identifiables` that are passed into the function
            # may be passed in as a string id, or as the object itself
            # If they are passed in as a string id, we need to get the object
            # from the registry
            _args, _kwargs = [], {}
            for k, v in fn_bound_arguments.items():
                if k in identifiables:
                    # Dereference the argument if it was passed in as a string id
                    if not isinstance(v, str):
                        # Not a string id, so just use the object
                        _kwargs[k] = v
                    else:
                        if isinstance(v, IdentifiableMixin):
                            # v is a string, but it is also an IdentifiableMixin
                            # e.g. Store("foo"), so just use v as is
                            _kwargs[k] = v
                        else:
                            # v is a string id
                            try:
                                # Directly try to look up the string id in the
                                # registry of the annotated type
                                _kwargs[k] = identifiables[k].from_id(v)
                            except Exception:
                                # If that fails, try to look up the string id in
                                # the Node registry, and then get the object
                                # from the Node
                                try:
                                    _kwargs[k] = Node.from_id(v).obj
                                except Exception as e:
                                    # If that fails and the object is a non-id string,
                                    # then just use the string as is.
                                    # We have to do this check here rather than above
                                    # because we want to make sure we check for all
                                    # identifiable and nodes before checking if the
                                    # string is just a string.
                                    # this is required for compatibility with
                                    # IdentifiableMixin objects that do not start with
                                    # the meerkat id prefix.
                                    if isinstance(v, str) and not is_meerkat_id(v):
                                        _kwargs[k] = v
                                    else:
                                        raise e
                else:
                    if k == "args":
                        # These are *args under the `args` key
                        # These are the only arguments that will be passed in as
                        # *args to the fn
                        v = [_resolve_id_to_obj(_value) for _value in v]
                        _args, _ = _unpack_stores_from_object(v)
                    elif k == "kwargs":
                        # These are **kwargs under the `kwargs` key
                        v = {_k: _resolve_id_to_obj(_value) for _k, _value in v.items()}
                        v, _ = _unpack_stores_from_object(v)
                        _kwargs = {**_kwargs, **v}
                    else:
                        # All other positional arguments that were not *args were
                        # bound, so they become kwargs
                        v, _ = _unpack_stores_from_object(_resolve_id_to_obj(v))
                        _kwargs[k] = v

            try:
                with unmarked():
                    # Run the function
                    result = fn(*_args, **_kwargs)
            except Exception as e:
                # If the function raises an exception, log it and return
                # the exception
                # In case the exception is about .set() being missing, add
                # a more helpful error message
                if "no attribute 'set'" in str(e):
                    # Get the name of the object that was passed in
                    # as a Store, but did not have a .set() method
                    obj_name = str(e).split("'")[1].strip("'")
                    # Update the error message to be more helpful
                    e = AttributeError(
                        f"Exception raised in endpoint `{fn.__name__}`. "
                        f"The object of type `{obj_name}` that you called to "
                        "update with `.set()` "
                        "is not a `Store`. You probably forgot to "
                        "annotate this object's typehint in the signature of "
                        f"`{fn.__name__}` as a `Store` i.e. \n\n"
                        "@endpoint\n"
                        f"def {fn.__name__}(..., parameter: Store, ...):\n\n"
                        "Remember that without this type annotation, the object "
                        "will be automatically unpacked by Meerkat inside the endpoint "
                        "if it is a `Store`."
                    )

                logger.exception(e)
                raise e

            # Return the result of the function
            return result

        # Register the endpoint and return it
        endpoint = Endpoint(
            fn=wrapper,
            prefix=prefix,
            route=route,
        )
        endpoint.add_route(method)
        return endpoint

    return _endpoint(fn)


def endpoints(cls: type = None, prefix: str = None):
    """Decorator to mark a class as containing a collection of endpoints. All
    instance methods in the marked class will be converted to endpoints.

    This decorator is useful when you want to create a class that
    contains some logical state variables (e.g. a Counter class), along
    with methods to manipulate the values of those variables (e.g.
    increment or decrement the counter).
    """

    if cls is None:
        return partial(endpoints, prefix=prefix)

    _ids = {}
    _max_ids = {}
    if cls not in _ids:
        _ids[cls] = {}
        _max_ids[cls] = 1

    def _endpoints(cls):
        class EndpointClass:
            def __init__(self, *args, **kwargs):
                self.instance = cls(*args, **kwargs)
                self.endpoints = {}

                # Access all the user-defined attributes of the instance
                # to create endpoints
                for attrib in dir(self.instance):
                    if attrib.startswith("__"):
                        continue
                    obj = self.instance.__getattribute__(attrib)
                    if callable(obj):
                        if attrib not in self.endpoints:
                            self.endpoints[attrib] = endpoint(
                                obj, prefix=prefix + f"/{_ids[cls][self]}"
                            )

            def __getattribute__(self, attrib):
                if self not in _ids[cls]:
                    _ids[cls][self] = _max_ids[cls]
                    _max_ids[cls] += 1

                try:
                    obj = super().__getattribute__(attrib)
                    return obj
                except AttributeError:
                    pass

                obj = self.instance.__getattribute__(attrib)
                if callable(obj):
                    if attrib not in self.endpoints:
                        return obj
                    return self.endpoints[attrib]
                else:
                    return obj

        return EndpointClass

    return _endpoints(cls)


def get_signature(fn: Union[Callable, Endpoint]) -> inspect.Signature:
    """Get the signature of a function or endpoint.

    Args:
        fn: The function or endpoint to get the signature of.

    Returns:
        The signature of the function or endpoint.
    """
    if isinstance(fn, Endpoint):
        fn = fn.fn
    return inspect.signature(fn)


def _resolve_id_to_obj(value):
    if isinstance(value, str) and is_meerkat_id(value):
        # This is a string that corresponds to a meerkat id,
        # so look it up.
        return Node.from_id(value).obj
    return value


def _is_annotation_store(type_hint) -> bool:
    """Check if a type hint is a Store or a Union of Stores.

    Returns True if:
        - The type hint is a Store
        - The type hint is a Union of Store and other non-Store values.
        - The type hint is a generic store Store[T] or Union[Store[T], ...]
    """
    if isinstance(type_hint, type) and issubclass(type_hint, Store):
        return True

    if isinstance(type_hint, typing._GenericAlias):
        origin = get_type_hint_origin(type_hint)
        args = get_type_hint_args(type_hint)

        if origin == typing.Union:
            return any(_is_annotation_store(arg) for arg in args)
        elif issubclass(origin, Store):
            return True

    return False
