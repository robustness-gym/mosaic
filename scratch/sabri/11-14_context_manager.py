"""Test the context manager with stores."""
# import meerkat as mk


# # Example 1
# s1 = mk.gui.Store(5)

# with mk.gui.react():
#     r = s1 + 2

# # the interface_op decorator should be applied to the addition method.
# # Thus:
# # 1. r should be a store because it is in mk.gui.react()
# # 2. r should be on the graph.
# assert isinstance(r, mk.gui.Store), type(r)
# # assert r.has_trigger_children()


import meerkat as mk

value = []




@mk.gui.endpoint
def reassign(value: mk.gui.Store):
    value.set(value + 1)
    print(value)


@mk.gui.reactive
def filter(df: mk.DataFrame, value: int):
    return df.lz[10 * value :]


df = mk.get("imagenette", version="160px")

df["new_col"] = 1

with mk.gui.react():
    value = mk.gui.Store(0)
    button = mk.gui.Button("Increment", on_click=reassign.partial(value))

    df = filter(df, value)

    filter_component = mk.gui.Filter(df, criteria=[], title="Filter Examples")
    df = filter_component(df)

    gallery = mk.gui.Gallery(df, main_column="img", tag_columns=["label"])


mk.gui.start()
mk.gui.Interface(components=[button, filter_component, gallery]).launch()