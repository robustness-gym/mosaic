import pytest

import meerkat as mk


@pytest.mark.parametrize("react", [False, True])
def test_store_reactive_math(react: bool):
    """Test basic math methods are reactive.

    A method is reactive if it:
        1. Returns a Store
        2. Creates a connection based on the op.
    """
    store = mk.gui.Store(1)

    expected = {
        "add": 2,
        "sub": 0,
        "mul": 1,
        "truediv": 1,
        "floordiv": 1,
        "mod": 0,
        # "divmod": (1, 0),
        "pow": 1,
        "neg": -1,
        "pos": 1,
        "abs": 1,
        "lt": False,
        "le": True,
        "eq": True,
        "ne": False,
        "gt": False,
        "ge": True,
    }

    out = {}
    with mk.gui.react(reactive=react, nested_return=False):
        out["add"] = store + 1
        out["sub"] = store - 1
        out["mul"] = store * 1
        out["truediv"] = store.__truediv__(1)
        out["floordiv"] = store // 1
        out["mod"] = store % 1
        # out["divmod"] = divmod(store, 1)
        out["pow"] = store**1
        out["neg"] = -store
        out["pos"] = +store
        out["abs"] = abs(store)
        out["lt"] = store < 1
        out["le"] = store <= 1
        out["eq"] = store == 1
        out["ne"] = store != 1
        out["gt"] = store > 1
        out["ge"] = store >= 1

    for k, v in out.items():
        if react:
            assert isinstance(v, mk.gui.Store)
            assert store.inode.has_trigger_children()
            # TODO: Check the parent of the current child.
        else:
            assert not isinstance(v, mk.gui.Store)
            assert store.inode is None

        assert v == expected[k]


@pytest.mark.parametrize("other", [1, 2])
def test_store_imethod(other):
    """Test traditional inplace methods are reactive, but return different
    stores."""
    store = original = mk.gui.Store(1)

    expected = {
        "__iadd__": store + other,
        "__isub__": store - other,
        "__imul__": store * other,
        "__itruediv__": store.__itruediv__(other),
        "__ifloordiv__": store // other,
        "__imod__": store % other,
        "__ipow__": store**other,
        "__ilshift__": store << other,
        "__irshift__": store >> other,
        "__iand__": store & other,
        "__ixor__": store ^ other,
        "__ior__": store | other,
    }

    out = {}
    with mk.gui.react():
        for k in expected:
            out[k] = getattr(store, k)(other)

    for k, v in out.items():
        assert isinstance(v, mk.gui.Store), f"{k} did not return a Store."
        assert id(v) != id(original), f"{k} did not return a new Store."
        assert v == expected[k], f"{k} did not return the correct value."