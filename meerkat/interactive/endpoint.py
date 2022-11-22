from __future__ import annotations
import inspect
from functools import partial, wraps
from typing import Any, Callable, Generic, Union

from fastapi import APIRouter, Body
from pydantic import BaseModel, create_model

from meerkat.interactive.graph import Store, trigger
from meerkat.interactive.node import Node, NodeMixin
from meerkat.interactive.types import T
from meerkat.mixins.identifiable import IdentifiableMixin
from meerkat.state import state


class SingletonRouter(type):
    """
    A metaclass that ensures that only one instance of a router is created
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
    #TODO: using the SingletonRouter metaclass causes a bug. 
    # app.include_router() inside Endpoint is called multiple times
    # for the same router. This causes an error because some 
    # endpoints are registered multiple times because the FastAPI
    # class doesn't check if an endpoint is already registered.
    # As a patch, we're generating one router per Endpoint object
    # (this could generate multiple routers for the same prefix, but
    # that's not a problem).
    """
    A very simple FastAPI router.

    Only one instance of this router will be created *for a given prefix*, so
    you can call this router multiple times in your code and it will always
    return the same instance.

    This router allows you to pass in arbitrary keyword arguments that are
    passed to the FastAPI router, and sets sensible defaults for the
    prefix, tags, and responses.

    Attributes:
        prefix (str): The prefix for this router.
        **kwargs: Arbitrary keyword arguments that are passed to the FastAPI
            router.

    Example:
        >>> from meerkat.interactive.api.routers import SimpleRouter
        >>> router = SimpleRouter(prefix="/endpoint")
        >>> router = SimpleRouter(prefix="/endpoint")
        >>> router is SimpleRouter(prefix="/endpoint")
        True
    """

    _self_identifiable_group: str = "routers"

    def __init__(self, prefix: str, **kwargs):
        super().__init__(
            prefix=prefix,
            tags=[prefix.strip("/").replace("/", "-")],
            responses={404: {"description": "Not found"}},
            id=prefix,
            **kwargs,
        )


class EndpointConfig(BaseModel):
    endpoint_id: Union[str, None]


# TODO: technically Endpoint doesn't need to be NodeMixin (probably)
class Endpoint(IdentifiableMixin, NodeMixin, Generic[T]):
    """
    Create an endpoint from a function in Meerkat.

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

    EmbeddedBody = partial(Body, embed=True)

    _self_identifiable_group: str = "endpoints"

    def __init__(
        self,
        fn: Callable = None,
        prefix: Union[str, APIRouter] = None,
        route: str = None,
    ):
        super().__init__()
        if fn is None:
            self.id = None
        self.fn = fn

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

    @property
    def config(self):
        return EndpointConfig(
            endpoint_id=self.id,
        )

    def run(self, *args, **kwargs) -> Any:
        """
        Actually run the endpoint function `fn`.

        Args:
            *args: Positional arguments to pass to `fn`.
            **kwargs: Keyword arguments to pass to `fn`.

        Returns:
            The return value of `fn`.
        """

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
            [param.default != param.empty for param in signature.parameters.values()]
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
        result = partial_fn()
        # Don't track modifications outside of the endpoint
        state.modification_queue.unready()

        modifications = trigger()

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

        return Endpoint(
            fn=partial(self.fn, *args, **kwargs),
            prefix=None,
            route=None,
        )

    def compose(self, fn: Union[Endpoint, callable]) -> Endpoint:
        """Create a new Endpoint that applies `fn` to the return value of this
        Endpoint.
        Effectively equivalent to `fn(self.fn(*args, **kwargs))`.

        Args:
            fn (Endpoint, callable): An Endpoint or a callable function that accepts
                a single argument of the same type as the return of this Endpoint
                (i.e. self).

        Return:
            Endpoint: The new composed Endpoint.
        """

        @wraps(self.fn)
        def composed(*args, **kwargs):
            return fn(self.fn(*args, **kwargs))

        return Endpoint(
            fn=composed,
            prefix=self.prefix,
            route=self.route,
        )

    def add_route(self, method: str = "POST") -> None:
        """
        Add a FastAPI route for this endpoint to the router. This
        function will not do anything if the router is None (i.e.
        no prefix was specified).

        This function is called automatically when the endpoint
        is created using the `endpoint` decorator.
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
            #   (e.g. `Store` -> `str`, `Reference` -> `str`)
            signature = inspect.signature(self.fn)

            pydantic_model_params = {}
            for p in signature.parameters:
                annot = signature.parameters[p].annotation
                default = signature.parameters[p].default
                has_default = default is not inspect._empty

                if annot is inspect.Parameter.empty:
                    assert (
                        has_default
                    ), f"Parameter {p} must have a type annotation or a default value."
                elif isinstance(annot, type) and issubclass(annot, IdentifiableMixin):
                    # e.g. Stores, References must be referred to by str ids when
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
            FnPydanticModel = create_model(
                f"{self.fn.__name__.capitalize()}Model",
                __config__=Config,
                **pydantic_model_params,
            )

            # Create a wrapper function, with kwargs that conform to the
            # Pydantic model, and a return annotation that matches `fn`
            def _fn(kwargs: FnPydanticModel) -> signature.return_annotation:
                return self.fn(**kwargs.dict())

            # def _fn(kwargs: Endpoint.EmbeddedBody()) -> signature.return_annotation:
            #     return self.fn(**kwargs)

            # Name the wrapper function the same as `fn`, so it looks nice
            # in the docs
            _fn.__name__ = self.fn.__name__
        else:
            signature = inspect.signature(self.fn)
            for p in signature.parameters:
                annot = signature.parameters[p].annotation

                # If annot is a subclass of `IdentifiableMixin`, replace
                # it with the `str` type (i.e. the id of the Identifiable)
                # (e.g. `Store` -> `str`, `Reference` -> `str`)
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

    def __call__(self, *args, **kwargs):
        """Calling the endpoint will just call the raw underlying function."""
        return self.fn(*args, **kwargs)


def make_endpoint(endpoint_or_fn: Union[Callable, Endpoint, None]) -> Endpoint:
    """Make an Endpoint."""
    return (
        endpoint_or_fn
        if isinstance(endpoint_or_fn, Endpoint)
        else Endpoint(endpoint_or_fn)
    )


def endpoint(
    fn: Callable = None,
    prefix: Union[str, APIRouter] = None,
    route: str = None,
    method: str = "POST",
):
    """
    Decorator to mark a function as an endpoint.

    An endpoint is a function that can be called to
        - update the value of a Store (e.g. incrementing a counter)
        - update an object referenced by a Reference (e.g. editing the
            contents of a DataFrame)
        - run a computation and return its result to the frontend
        - run a function in response to a frontend event (e.g. button
            click)

    Endpoints differ from operations in that they are not automatically
    triggered by changes in their inputs. Instead, they are triggered by
    explicit calls to the endpoint function.

    The Store and Reference objects that are modified inside the endpoint
    function will automatically trigger operations in the graph that
    depend on them.

    Warning: Due to this, we do not recommend running endpoints manually
    in your Python code. This can lead to unexpected behavior e.g.
    running an endpoint inside an operation may change a Store or
    Reference  that causes the operation to be triggered repeatedly,
    leading to an infinite loop.

    Almost all use cases can be handled by using the frontend to trigger
    endpoints.

    .. code-block:: python

        @endpoint
        def increment(count: Store, step: int = 1):
            count._ += step
            # ^ update the count Store, which will trigger operations
            #   that depend on it

            # return the updated value to the frontend
            return count._

        # Now you can create a button that calls the increment endpoint
        counter = Store(0)
        button = Button(on_click=increment(counter))
        # ^ read this as: call the increment endpoint with the counter
        # Store when the button is clicked

    Args:
        fn: The function to decorate.

    Returns:
        The decorated function, as an Endpoint object.
    """
    if fn is None:
        return partial(endpoint, prefix=prefix, route=route, method=method)

    def _endpoint(fn: Callable):
        # Gather up all the arguments that are hinted as Stores and References
        stores = set()
        # Also gather up the hinted arguments that subclass IdentifiableMixin
        # e.g. Store, Reference, Endpoint, Interface, etc.
        identifiables = {}
        for name, annot in inspect.getfullargspec(fn).annotations.items():
            if isinstance(annot, type) and issubclass(annot, Store):
                stores.add(name)

            # Add all the identifiables
            if isinstance(annot, type) and issubclass(annot, IdentifiableMixin):
                identifiables[name] = annot

        @wraps(fn)
        def wrapper(*args, **kwargs):
            """

            Subsequent calls to the function will be handled by the graph.
            """
            # Keep the arguments that were not annotated to be stores or
            # references
            fn_signature = inspect.signature(fn)
            fn_bound_arguments = fn_signature.bind(*args, **kwargs).arguments

            # Identifiables that are passed into the function
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
                                _kwargs[k] = Node.from_id(v).obj
                else:
                    if k == "args":
                        # These are *args under the `args` key
                        # These are the only arguments that will be passed in as
                        # *args to the fn
                        _args = v
                    elif k == "kwargs":
                        # These are **kwargs under the `kwargs` key
                        _kwargs = {**_kwargs, **v}
                    else:
                        # All other positional arguments that were not *args were
                        # bound, so they become kwargs
                        _kwargs[k] = v

            # Run the function
            result = fn(*_args, **_kwargs)

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
