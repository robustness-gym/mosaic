import logging
import warnings
from typing import Any, Generic, Iterator, List, Tuple, TypeVar, Union

from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ValidationError
from pydantic.v1.fields import ModelField
from wrapt import ObjectProxy

from meerkat.interactive.graph.magic import _magic, is_magic_context
from meerkat.interactive.graph.marking import is_unmarked_context, unmarked
from meerkat.interactive.graph.reactivity import reactive
from meerkat.interactive.modification import StoreModification
from meerkat.interactive.node import NodeMixin
from meerkat.interactive.types import Storeable
from meerkat.interactive.utils import get_custom_json_encoder
from meerkat.mixins.identifiable import IdentifiableMixin
from meerkat.mixins.reactifiable import MarkableMixin

__all__ = ["Store", "StoreFrontend", "make_store"]
logger = logging.getLogger(__name__)


class StoreFrontend(BaseModel):
    store_id: str
    value: Any
    has_children: bool
    is_store: bool = True


T = TypeVar("T")


# ObjectProxy must be the last base class
class Store(IdentifiableMixin, NodeMixin, MarkableMixin, Generic[T], ObjectProxy):
    _self_identifiable_group: str = "stores"
    # By default, stores are marked.
    _self_marked = True

    def __init__(self, wrapped: T, backend_only: bool = False):
        super().__init__(wrapped=wrapped)

        if not isinstance(self, _IteratorStore) and isinstance(wrapped, Iterator):
            warnings.warn(
                "Wrapping an iterator in a Store is not recommended. "
                "If the iterator is derived from an iterable, wrap the iterable:\n"
                "    >>> store = mk.Store(iterable)\n"
                "    >>> iterator = iter(store)"
            )

        # Set up these attributes so we can create the
        # schema and detail properties.
        self._self_schema = None
        self._self_detail = None
        self._self_value = None
        self._self_backend_only = backend_only

    @property
    def value(self):
        return self.__wrapped__

    def to_json(self) -> Any:
        """Converts the wrapped object into a jsonifiable object."""
        return jsonable_encoder(
            self.__wrapped__, custom_encoder=get_custom_json_encoder()
        )

    @property
    def frontend(self):
        return StoreFrontend(
            store_id=self.id,
            value=self.__wrapped__,
            has_children=self.inode.has_children() if self.inode else False,
        )

    @property
    def detail(self):
        return f"Store({self.__wrapped__}) has id {self.id} and node {self.inode}"

    def set(self, new_value: T) -> None:
        """Set the value of the store.

        This will trigger any reactive functions that depend on this store.

        Args:
            new_value (T): The new value of the store.

        Returns:
            None

        Note:
            Even if the new_value is the same as the current value, this will
            still trigger any reactive functions that depend on this store.
            To avoid this, check for equality before calling this method.
        """
        if isinstance(new_value, Store):
            # if the value is a store, then we need to unpack so it can be sent to the
            # frontend
            new_value = new_value.__wrapped__

        logging.debug(f"Setting store {self.id}: {self.value} -> {new_value}.")

        # TODO: Find operations that depend on this store and edit the cache.
        # This should be done in the StoreModification
        mod = StoreModification(id=self.id, value=new_value)
        self.__wrapped__ = new_value
        mod.add_to_queue()

    @unmarked()
    def __repr__(self) -> str:
        return f"{type(self).__name__}({repr(self.__wrapped__)})"

    def __getattr__(self, name: str) -> Any:
        # This method is only run when the attribute is not found in the class.
        # In this case, we will always punt the call to the wrapped object.

        # Only create a reactive function if we are not in an unmarked context
        # This is like creating another `getattr` function that is reactive
        # and calling it with `self` as the first argument.
        if is_magic_context():

            @_magic
            def wrapper(wrapped, name: str = name):
                return getattr(wrapped, name)

            # Note: this will work for both methods and properties.
            return wrapper(self)
        else:
            # Otherwise, just return the `attr` as is.
            return getattr(self.__wrapped__, name)

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v, field: ModelField):
        if not isinstance(v, cls):
            if not field.sub_fields:
                # Generic parameters were not provided so we don't try to validate
                # them and just return the value as is
                return cls(v)
            else:
                # Generic parameters were provided so we try to validate them
                # and return a Store object
                v, error = field.sub_fields[0].validate(v, {}, loc="value")
                if error:
                    raise ValidationError(error)
                return cls(v)
        return v

    def __hash__(self):
        return hash(self.__wrapped__)

    @reactive()
    def __call__(self, *args, **kwargs):
        return self.__wrapped__(*args, **kwargs)

    @reactive()
    def __lt__(self, other):
        return super().__lt__(other)

    @reactive()
    def __le__(self, other):
        return super().__le__(other)

    @reactive()
    def __eq__(self, other):
        return super().__eq__(other)

    @reactive()
    def __ne__(self, other):
        return super().__ne__(other)

    @reactive()
    def __gt__(self, other):
        return super().__gt__(other)

    @reactive()
    def __ge__(self, other):
        return super().__ge__(other)

    @_magic
    def __nonzero__(self):
        return super().__nonzero__()

    # @reactive()
    # def to_str(self):
    #     return super().__str__()

    @reactive()
    def __add__(self, other):
        return super().__add__(other)

    @reactive()
    def __sub__(self, other):
        return super().__sub__(other)

    @reactive()
    def __mul__(self, other):
        return super().__mul__(other)

    @reactive()
    def __div__(self, other):
        return super().__div__(other)

    @reactive()
    def __truediv__(self, other):
        return super().__truediv__(other)

    @reactive()
    def __floordiv__(self, other):
        return super().__floordiv__(other)

    @reactive()
    def __mod__(self, other):
        return super().__mod__(other)

    @reactive(nested_return=False)
    def __divmod__(self, other):
        return super().__divmod__(other)

    @reactive()
    def __pow__(self, other, *args):
        return super().__pow__(other, *args)

    @reactive()
    def __lshift__(self, other):
        return super().__lshift__(other)

    @reactive()
    def __rshift__(self, other):
        return super().__rshift__(other)

    @reactive()
    def __and__(self, other):
        return super().__and__(other)

    @reactive()
    def __xor__(self, other):
        return super().__xor__(other)

    @reactive()
    def __or__(self, other):
        return super().__or__(other)

    @reactive()
    def __radd__(self, other):
        return super().__radd__(other)

    @reactive()
    def __rsub__(self, other):
        return super().__rsub__(other)

    @reactive()
    def __rmul__(self, other):
        return super().__rmul__(other)

    @reactive()
    def __rdiv__(self, other):
        return super().__rdiv__(other)

    @reactive()
    def __rtruediv__(self, other):
        return super().__rtruediv__(other)

    @reactive()
    def __rfloordiv__(self, other):
        return super().__rfloordiv__(other)

    @reactive()
    def __rmod__(self, other):
        return super().__rmod__(other)

    @reactive()
    def __rdivmod__(self, other):
        return super().__rdivmod__(other)

    @reactive()
    def __rpow__(self, other, *args):
        return super().__rpow__(other, *args)

    @reactive()
    def __rlshift__(self, other):
        return super().__rlshift__(other)

    @reactive()
    def __rrshift__(self, other):
        return super().__rrshift__(other)

    @reactive()
    def __rand__(self, other):
        return super().__rand__(other)

    @reactive()
    def __rxor__(self, other):
        return super().__rxor__(other)

    @reactive()
    def __ror__(self, other):
        return super().__ror__(other)

    @reactive()
    def __neg__(self):
        return super().__neg__()

    @reactive()
    def __pos__(self):
        return super().__pos__()

    @_magic
    def __abs__(self):
        return super().__abs__()

    @reactive()
    def __invert__(self):
        return super().__invert__()

    # We do not need to decorate i-methods because they call their
    # out-of-place counterparts, which are reactive
    def __iadd__(self, other):
        warnings.warn(
            f"{type(self).__name__}.__iadd__ is out-of-place. Use __add__ instead."
        )
        return self.__add__(other)

    def __isub__(self, other):
        warnings.warn(
            f"{type(self).__name__}.__isub__ is out-of-place. Use __sub__ instead."
        )
        return self.__sub__(other)

    def __imul__(self, other):
        warnings.warn(
            f"{type(self).__name__}.__imul__ is out-of-place. Use __mul__ instead."
        )
        return self.__mul__(other)

    def __idiv__(self, other):
        warnings.warn(
            f"{type(self).__name__}.__idiv__ is out-of-place. Use __div__ instead."
        )
        return self.__div__(other)

    def __itruediv__(self, other):
        warnings.warn(
            f"{type(self).__name__}.__itruediv__ is out-of-place. "
            "Use __truediv__ instead."
        )
        return self.__truediv__(other)

    def __ifloordiv__(self, other):
        warnings.warn(
            f"{type(self).__name__}.__ifloordiv__ is out-of-place. "
            "Use __floordiv__ instead."
        )
        return self.__floordiv__(other)

    def __imod__(self, other):
        warnings.warn(
            f"{type(self).__name__}.__imod__ is out-of-place. Use __mod__ instead."
        )
        return self.__mod__(other)

    def __ipow__(self, other):
        warnings.warn(
            f"{type(self).__name__}.__ipow__ is out-of-place. Use __pow__ instead."
        )
        return self.__pow__(other)

    def __ilshift__(self, other):
        warnings.warn(
            f"{type(self).__name__}.__ilshift__ is out-of-place. "
            "Use __lshift__ instead."
        )
        return self.__lshift__(other)

    def __irshift__(self, other):
        warnings.warn(
            f"{type(self).__name__}.__irshift__ is out-of-place. "
            "Use __rshift__ instead."
        )
        return self.__rshift__(other)

    def __iand__(self, other):
        warnings.warn(
            f"{type(self).__name__}.__iand__ is out-of-place. Use __and__ instead."
        )
        return self.__and__(other)

    def __ixor__(self, other):
        warnings.warn(
            f"{type(self).__name__}.__ixor__ is out-of-place. Use __xor__ instead."
        )
        return self.__xor__(other)

    def __ior__(self, other):
        warnings.warn(
            f"{type(self).__name__}.__ior__ is out-of-place. Use __or__ instead."
        )
        return self.__or__(other)

    # While __index__ must return an integer, we decorate it with @reactive().
    # This means that any calls to __index__ when the store is marked will
    # return a Store, which will raise a TypeError.
    # We do this to make sure that wrapper methods calling __index__
    # handle non-integer values appropriately.
    # NOTE: This only works if __index__ is always called from wrapper methods
    # and the user/developer has a way of intercepting these methods or creating
    # recommended practices for avoiding this error.
    @reactive()
    def __index__(self):
        return super().__index__()

    def _reactive_warning(self, name):
        # If the context is not unmarked and the store is operating in a magic
        # context, this method will raise a warning.
        # This will primarily be done by __dunder__ methods, which are called by
        # builtin Python functions (e.g. __len__ -> len, __int__ -> int, etc.)
        if not is_unmarked_context() and is_magic_context():
            warnings.warn(
                f"Calling {name}(store) is not reactive. Use `mk.{name}(store)` to get"
                f"a reactive variable (i.e. a Store). `mk.{name}(store)` behaves"
                f"exactly like {name}(store) outside of this difference."
            )

    # Don't use @_wand on:
    #   - __len__
    #   - __int__
    #   - __long__
    #   - __float__
    #   - __complex__
    #   - __oct__
    #   - __hex__
    # Python requires that these methods must return a primitive type
    # (i.e. not a Store). As such, we cannot wrap them in @reactive using
    # @_wand.
    # We allow the user to call these methods on stores (e.g. len(store)),
    # which will return the appropriate primitive type (i.e. not reactive).
    # We raise a warning to remind the user that these methods are not reactive.
    def __len__(self):
        self._reactive_warning("len")
        return super().__len__()

    def __int__(self):
        self._reactive_warning("int")
        return super().__int__()

    def __long__(self):
        self._reactive_warning("long")
        return super().__long__()

    def __float__(self):
        self._reactive_warning("float")
        return super().__float__()

    def __complex__(self):
        self._reactive_warning("complex")
        return super().__complex__()

    def __oct__(self):
        self._reactive_warning("oct")
        return super().__oct__()

    def __hex__(self):
        self._reactive_warning("hex")
        return super().__hex__()

    def __bool__(self):
        self._reactive_warning("bool")
        return super().__bool__()

    @_magic
    def __contains__(self, value):
        return super().__contains__(value)

    @reactive(nested_return=False)
    def __getitem__(self, key):
        return super().__getitem__(key)

    # TODO(Arjun): Check whether this needs to be reactive.
    # @reactive
    # def __setitem__(self, key, value):
    #     print("In setitem", self, "key", key, "value", value, "type", type(value))
    #     # Make a shallow copy of the value because this operation is not in-place.
    #     obj = self.__wrapped__.copy()
    #     obj[key] = value
    #     warnings.warn(f"{type(self).__name__}.__setitem__ is out-of-place.")
    #     return type(self)(obj, backend_only=self._self_backend_only)

    @_magic
    def __delitem__(self, key):
        obj = self.__wrapped__.copy()
        del obj[key]
        warnings.warn(f"{type(self).__name__}.__delitem__ is out-of-place.")
        return type(self)(obj, backend_only=self._self_backend_only)

    @reactive(nested_return=False)
    def __getslice__(self, i, j):
        return super().__getslice__(i, j)

    # # TODO(Arjun): Check whether this needs to be reactive.
    # @_wand
    # def __setslice__(self, i, j, value):
    #     obj = self.__wrapped__.copy()
    #     obj[i:j] = value
    #     warnings.warn(f"{type(self).__name__}.__setslice__ is out-of-place.")
    #     return type(self)(obj, backend_only=self._self_backend_only)

    @_magic
    def __delslice__(self, i, j):
        obj = self.__wrapped__.copy()
        del obj[i:j]
        warnings.warn(f"{type(self).__name__}.__delslice__ is out-of-place.")
        return type(self)(obj, backend_only=self._self_backend_only)

    # def __enter__(self):
    #     return self.__wrapped__.__enter__()

    # def __exit__(self, *args, **kwargs):
    #     return self.__wrapped__.__exit__(*args, **kwargs)

    # Overriding __next__ causes issues when using Stores with third-party libraries.
    # @reactive
    # def __next__(self):
    #     return next(self.__wrapped__)

    # @_wand: __iter__ behaves like a @_wand method, but cannot be decorated due to
    # Pythonic limitations
    @reactive()
    def __iter__(self):
        return iter(self.__wrapped__)


class _IteratorStore(Store):
    """A special store that wraps an iterator."""

    def __init__(self, wrapped: T, backend_only: bool = False):
        if not isinstance(wrapped, Iterator):
            raise ValueError("wrapped object must be an Iterator.")
        super().__init__(wrapped, backend_only=backend_only)

    @reactive()
    def __next__(self):
        return next(self.__wrapped__)


def make_store(value: Union[str, Storeable]) -> Store:
    """Make a Store.

    If value is a Store, return it. Otherwise, return a
    new Store that wraps value.

    Args:
        value (Union[str, Storeable]): The value to wrap.

    Returns:
        Store: The Store wrapping value.
    """
    return value if isinstance(value, Store) else Store(value)


def _unpack_stores_from_object(
    obj: Any, unpack_nested: bool = False
) -> Tuple[Any, List[Store]]:
    """Unpack all the `Store` objects from a given object.

    By default, if a store is nested inside another store,
    it is not unpacked. If `unpack_nested` is True, then all stores
    are unpacked.

    Args:
        obj: The object to unpack stores from.
        unpack_nested: Whether to unpack nested stores.

    Returns:
        A tuple of the unpacked object and a list of the stores.
    """
    # Must use no_react here so that calling a method on a `Store`
    # e.g. `obj.items()` doesn't return new `Store` objects.
    # Note: cannot use `no_react` as a decorator on this fn because
    # it will automatically unpack the stores in the arguments.
    with unmarked():
        if not unpack_nested and isinstance(obj, Store):
            return obj.value, [obj]

        _type = type(obj)
        if isinstance(obj, Store):
            _type = type(obj.value)

        if isinstance(obj, (list, tuple)):
            stores = []
            unpacked = []
            for x in obj:
                x, stores_i = _unpack_stores_from_object(x, unpack_nested)
                unpacked.append(x)
                stores.extend(stores_i)

            if isinstance(obj, Store):
                stores.append(obj)

            return _type(unpacked), stores
        elif isinstance(obj, dict):
            stores = []
            unpacked = {}
            for k, v in obj.items():
                k, stores_i_k = _unpack_stores_from_object(k, unpack_nested)
                v, stores_i_v = _unpack_stores_from_object(v, unpack_nested)
                unpacked[k] = v
                stores.extend(stores_i_k)
                stores.extend(stores_i_v)

            if isinstance(obj, Store):
                stores.append(obj)

            return _type(unpacked), stores
        elif isinstance(obj, slice):
            stores = []
            # TODO: Figure out if we should do unpack nested here.
            start, start_store = _unpack_stores_from_object(obj.start)
            stop, stop_store = _unpack_stores_from_object(obj.stop)
            step, step_store = _unpack_stores_from_object(obj.step)
            stores.extend(start_store)
            stores.extend(stop_store)
            stores.extend(step_store)
            return _type(start, stop, step), stores
        elif isinstance(obj, Store):
            return obj.value, [obj]
        else:
            return obj, []
