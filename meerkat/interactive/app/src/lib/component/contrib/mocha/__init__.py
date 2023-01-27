from meerkat.dataframe import DataFrame
import meerkat as mk
from meerkat.ops.sliceby.sliceby import SliceBy
from meerkat.interactive.app.src.lib.component.filter import FilterCriterion

import numpy as np
from ...abstract import BaseComponent

from mocha.repo import SliceRepo

DELTA_COLUMN = "delta"


class ChangeList(BaseComponent):
    
    def __init__(
        self,
        df: DataFrame,
        v1_column: str,
        v2_column: str,
        main_column: str,
        repo_path: str = None,
    ):
        if df.primary_key is None:
            raise ValueError("The DataFrame must have a primary key set.")

        df[DELTA_COLUMN] = df[v2_column] - df[v1_column]

        slice_repo = SliceRepo(df, repo_path)
        for i in range(3):
            slice_repo.add(
                f"slice_{i}",
                mk.DataFrame(
                    {
                        df.primary_key_name: df[df.primary_key_name],
                        "slice": np.random.rand(len(df)) > 0.9,
                    },
                    primary_key=df.primary_key_name,
                ),
            )

        membership_df = slice_repo.membership
        slices_df = slice_repo.slices
        base_examples = df

        with mk.gui.react():

            examples_df = mk.merge(base_examples, membership_df, on=df.primary_key_name)
            # SLICE OVERVIEW
            @mk.gui.reactive
            def compute_slice_scores(examples: mk.DataPanel, slices: mk.DataPanel):
                """Produce a DataFrame with average delta's (and counts) for each slice."""

                sb = examples.sliceby(
                    slices["slice_id"].apply(slice_repo._slice_column)
                )
                result = sb[DELTA_COLUMN].mean()

                # compute prototype image embeddings
                image_prototypes_df = sb[["clip_1", "clip_2", "clip_concat"]].mean(
                    axis=0
                )
                image_prototypes_df["slice_id"] = image_prototypes_df["slice"].map(
                    slice_repo._slice_id
                )
                image_prototypes_df.remove_column("slice")
                slices = slices.merge(image_prototypes_df, on="slice_id")

                # # Hacky way to rename DELTA_COLUMN column -> count
                count = sb[DELTA_COLUMN].count()
                count["count"] = count[DELTA_COLUMN]
                count = count[["slice", "count"]]
                result = result.merge(count, on="slice")

                result = result.sort(by=DELTA_COLUMN, ascending=False)

                slices["slice"] = slices["slice_id"].apply(slice_repo._slice_column)
                out = (
                    slices[
                        "slice_id",
                        "name",
                        "description",
                        "slice",
                        "clip_1",
                        "clip_2",
                        "clip_concat",
                    ]
                    .merge(result, on="slice")
                    .drop("slice")
                )
                slices.remove_column("slice")
                return out

            stats_df = compute_slice_scores(examples=examples_df, slices=slices_df)

            @mk.gui.endpoint
            def append_to_sort(match_criterion, criteria: mk.gui.Store):
                SOURCE = "match"
                criterion = mk.gui.Sort.create_criterion(
                    column=match_criterion.name, ascending=False, source=SOURCE
                )

                criteria.set([criterion] + [c for c in criteria if c.source != SOURCE])

            sort_criteria = mk.gui.Store([])
            match = mk.gui.Match(
                df=base_examples,
                against="clip_1",
                title="Search Examples",
                on_match=append_to_sort.partial(criteria=sort_criteria),
            )
            examples_df, _ = match(examples_df)

            # sort the gallery
            sort = mk.gui.Sort(
                df=examples_df, criteria=sort_criteria, title="Sort Examples"
            )

            # the filter for the gallery
            # TODO(sabri): make this default to the active slice
            filter = mk.gui.Filter(df=examples_df, title="Filter Examples")
            examples_df = filter(examples_df)
            current_examples = sort(examples_df)

            # removing dirty entries does not use the returned criteria.
            # but we need to pass it as an argument so that the topological sort
            # runs this command after the match.
            slice_sort = mk.gui.Sort(df=stats_df, criteria=[], title="Sort Slices")

            sb_match = mk.gui.Match(
                df=stats_df,
                against="clip_1",
                title="Search Slices",
                on_match=append_to_sort.partial(criteria=slice_sort.criteria),
            )
            stats_df, _ = sb_match()

            stats_df = slice_sort(stats_df)

            selected_slice_id = mk.gui.Store("")

            @mk.gui.endpoint
            def on_select_slice(
                slice_id: str, criteria: mk.gui.Store, selected: mk.gui.Store
            ):
                """Update the gallery filter criteria with the selected slice.

                The gallery should be filtered based on the selected slice.
                If no slice is selected, there shouldn't be any filtering based on the slice.
                When the selected slice is changed, we should replace the existing filter criteria
                with the new one.
                """
                source = "on_select_slice"
                wrapped = [
                    x if isinstance(x, FilterCriterion) else FilterCriterion(**x)
                    for x in criteria
                ]
                on_select_criterion = [x for x in wrapped if x.source == source]
                assert (
                    len(on_select_criterion) <= 1
                ), "Something went wrong - Cannot have more than one selected slice"
                for x in on_select_criterion:
                    wrapped.remove(x)

                if slice_id:
                    wrapped.append(
                        FilterCriterion(
                            is_enabled=True,
                            column=slice_repo._slice_column(slice_id),
                            op="==",
                            value=True,
                            source=source,
                        )
                    )
                criteria.set(wrapped)
                # set to empty string if None
                # TODO: Need mk.None
                selected.set(slice_id or "")

                plot = mk.gui.Plot(
                    df=stats_df,
                    x=DELTA_COLUMN,
                    y="name",
                    x_label="Accuracy Shift (μ)",
                    y_label="slice",
                    metadata_columns=["count"],
                    keys_to_remove=[],
                    on_select=on_select_slice.partial(
                        criteria=filter.criteria, selected=selected_slice_id
                    ),
                )

                @mk.gui.endpoint
                def on_write_row(key: str, column: str, value: str, df: mk.DataFrame):
                    """Change the value of a column in the slice_df."""
                    if not key:
                        return
                    df[column][df.primary_key._keyidx_to_posidx(key)] = value
                    # We have to force add the dataframe modification to trigger downstream updates
                    mod = mk.gui.DataFrameModification(id=df.id, scope=[column])
                    mod.add_to_queue()

                active_slice_view = mk.gui.Row(
                    df=stats_df,
                    primary_key_column=slices_df.primary_key_name,
                    cell_specs={
                        "name": {"type": "editable"},
                        "description": {"type": "editable"},
                        DELTA_COLUMN: {"type": "stat", "name": "Accuracy Change"},
                        # "key": {"type": "stat"},
                        "count": {"type": "stat"},
                    },
                    selected_key=selected_slice_id,
                    title="Active Slice",
                    # The edits should be written on the slices_df
                    on_change=on_write_row.partial(df=slices_df),
                )

                gallery = mk.gui.Gallery(
                    df=current_examples,
                    main_column="image",
                    tag_columns=[DELTA_COLUMN, "target", "pred_a", "pred_b"],
                    # edit_target=edit_target,
                )

                @mk.gui.endpoint
                def add_discovered_slices(eb: SliceBy):
                    for key, slice in eb.slices.items():
                        col = np.zeros(len(slice_repo.membership))
                        col[slice] = 1
                        # FIXME: make this interface less awful
                        slice_repo.add(
                            name=f"discovered_{key}",
                            membership=mk.DataFrame(
                                {
                                    eb.data.primary_key_name: eb.data.primary_key,
                                    "slice": col,
                                },
                                primary_key=eb.data.primary_key_name,
                            ),
                        )

                    # add a sort by created time

                discover = mk.gui.Discover(
                    df=current_examples,
                    by="clip_1",
                    target="pred_a",
                    pred="pred_b",
                    on_discover=add_discovered_slices,
                )

                stats = mk.gui.Stats(data={"count": len(current_examples)})