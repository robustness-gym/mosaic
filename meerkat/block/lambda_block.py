from __future__ import annotations

import os
from copy import copy
from dataclasses import dataclass
from multiprocessing.sharedctypes import Value
from typing import Dict, Hashable, List, Sequence, Tuple, Union

import dill
import numpy as np
import yaml
from cytoolz import merge_with

import meerkat as mk
from meerkat.block.ref import BlockRef
from meerkat.columns.abstract import AbstractColumn
from meerkat.tools.utils import MeerkatLoader, translate_index

from .abstract import AbstractBlock, BlockIndex, BlockView


@dataclass
class LambdaCellOp:
    args: List[any]
    kwargs: Dict[str, any]
    fn: callable
    is_batched_fn: bool
    return_index: Union[str, int] = None

    @staticmethod
    def prepare_arg(arg):
        from ..columns.lambda_column import AbstractCell

        if isinstance(arg, AbstractCell):
            return arg.get()
        elif isinstance(arg, AbstractColumn):
            return arg[:]
        return arg

    def _get(self):

        args = [self.prepare_arg(arg) for arg in self.args]
        kwargs = {kw: self.prepare_arg(arg) for kw, arg in self.kwargs.items()}
        out = self.fn(*args, **kwargs)

        if self.return_index is not None:
            return out[self.return_index]

        if self.is_batched_fn:
            return out[0]

        return out

    def with_return_index(self, index: Union[str, int]):
        op = copy(self)
        op.return_index = index
        return op


@dataclass
class LambdaOp:
    args: List[mk.AbstractColumn]
    kwargs: Dict[str, mk.AbstractColumn]
    fn: callable
    is_batched_fn: bool
    batch_size: int
    return_format: type = None
    return_index: Union[str, int] = None

    @staticmethod
    def concat(ops: Sequence[LambdaOp]):
        """Concatenate a sequence of operations."""
        if len(ops) == 0:
            raise ValueError("Cannot concatenate empty sequence of LambdaOp.")

        if len(ops) == 1:
            return ops[0]

        # going to use the `fn` etc. of the first op
        op = copy(ops[0])

        op.args = [mk.concat([op.args[i] for op in ops]) for i in range(len(op.args))]
        op.kwargs = {
            kwarg: mk.concat([op.kwargs[kwarg] for op in ops])
            for kwarg in op.kwargs.keys()
        }
        return op

    def is_equal(self, other: AbstractColumn):
        if (
            self.fn != other.fn
            or self.is_batched_fn != other.is_batched_fn
            or self.return_format != other.return_format
            or self.return_index != other.return_index
        ):
            return False

        for arg, other_arg in zip(self.args, other.args):
            if not arg.is_equal(other_arg):
                return False

        if set(self.kwargs.keys()) != set(other.kwargs.keys()):
            return False

        for key in self.kwargs:
            if not self.kwargs[key].is_equal(other.kwargs[key]):
                return False
        return True

    def write(self, path: str, written_inputs: dict = None):
        """_summary_

        Args:
            path (str): _description_
            written_inputs (dict, optional): _description_. Defaults to None.

        """
        # Make all the directories to the path
        os.makedirs(path, exist_ok=True)

        if written_inputs is None:
            written_inputs = {}
        state = {
            "fn": self.fn,
            "return_index": self.return_index,
            "return_format": self.return_format,
            "is_batched_fn": self.is_batched_fn,
            "batch_size": self.batch_size,
        }
        state_path = os.path.join(path, "state.dill")
        dill.dump(state, open(state_path, "wb"))

        meta = {"args": [], "kwargs": {}}

        args_dir = os.path.join(path, "args")
        os.makedirs(args_dir, exist_ok=True)
        for idx, arg in enumerate(self.args):
            if id(arg) in written_inputs:
                meta["args"].append(written_inputs[id(arg)])
            else:
                col_path = os.path.join(args_dir, f"{idx}.col")
                arg.write(col_path)
                meta["args"].append(col_path)

        kwargs_dir = os.path.join(path, "kwargs")
        os.makedirs(kwargs_dir, exist_ok=True)
        for key, arg in self.kwargs.items():
            if id(arg) in written_inputs:
                meta["kwargs"][key] = written_inputs[id(arg)]
            else:
                col_path = os.path.join(kwargs_dir, f"{key}.col")
                arg.write(col_path)
                meta["kwargs"][key] = col_path

        # Save the metadata as a yaml file
        meta_path = os.path.join(path, "meta.yaml")
        yaml.dump(meta, open(meta_path, "w"))

    @classmethod
    def read(cls, path, read_inputs: dict = None):
        if read_inputs is None:
            read_inputs = {}

        # Assert that the path exists
        assert os.path.exists(path), f"`path` {path} does not exist."

        meta = dict(
            yaml.load(
                open(os.path.join(path, "meta.yaml")),
                Loader=MeerkatLoader,
            )
        )

        args = [
            read_inputs.get(arg_path, AbstractColumn.read(arg_path))
            for arg_path in meta["args"]
        ]
        kwargs = {
            key: read_inputs.get(kwarg_path, AbstractColumn.read(kwarg_path))
            for key, kwarg_path in meta["kwargs"]
        }

        state = dill.load(open(os.path.join(path, "state.dill"), "rb"))

        return cls(args=args, kwargs=kwargs, **state)

    def _get(
        self,
        index: Union[int, np.ndarray],
        indexed_inputs: dict = None,
        materialize: bool = True,
    ):
        if indexed_inputs is None:
            indexed_inputs = {}

        # if function is batched, but the index is singular, we need to turn the
        # single index into a batch index, and then later unpack the result
        single_on_batched = self.is_batched_fn and isinstance(index, int)
        if single_on_batched:
            index = np.array([index])

        # we pass results from other columns
        # prepare inputs
        kwargs = {
            # if column has already been indexed
            kwarg: indexed_inputs.get(
                id(column), column._get(index, materialize=materialize)
            )
            for kwarg, column in self.kwargs.items()
        }

        args = [
            indexed_inputs.get(id(column), column._get(index, materialize=materialize))
            for column in self.args
        ]

        if isinstance(index, int):
            if materialize:
                output = self.fn(*args, **kwargs)
                if self.return_index is not None:
                    output = output[self.return_index]
                return output
            else:
                return LambdaCellOp(
                    fn=self.fn,
                    args=args,
                    kwargs=kwargs,
                    is_batched_fn=self.is_batched_fn,
                    return_index=self.return_index,
                )

        elif isinstance(index, np.ndarray):
            if materialize:
                if self.is_batched_fn:
                    output = self.fn(*args, **kwargs)

                    if self.return_index is not None:
                        output = output[self.return_index]

                    if single_on_batched:
                        if (self.return_format is dict) and (self.return_index is None):
                            return {k: v[0] for k, v in output.items()}
                        elif (self.return_format is tuple) and (
                            self.return_index is None
                        ):
                            return [v[0] for v in output]
                        else:
                            return output[0]
                    return output

                else:
                    outputs = []
                    for i in range(len(index)):
                        output = self.fn(
                            *[arg[i] for arg in args],
                            **{kwarg: column[i] for kwarg, column in kwargs.items()},
                        )

                        if self.return_index is not None:
                            output = output[self.return_index]
                        outputs.append(output)

                    if (self.return_format is dict) and (self.return_index is None):
                        return merge_with(list, outputs)
                    elif (self.return_format is tuple) and (self.return_index is None):
                        return tuple(zip(*outputs))
                    else:
                        return outputs

            else:
                if single_on_batched:
                    return LambdaCellOp(
                        fn=self.fn,
                        args=args,
                        kwargs=kwargs,
                        is_batched_fn=self.is_batched_fn,
                        return_index=self.return_index,
                    )
                return LambdaOp(
                    fn=self.fn,
                    args=args,
                    kwargs=kwargs,
                    is_batched_fn=self.is_batched_fn,
                    batch_size=self.batch_size,
                    return_format=self.return_format,
                    return_index=self.return_index,
                )

    def __len__(self):
        if len(self.args) > 0:
            return len(self.args[0])
        else:
            for col in self.kwargs.values():
                return len(col)
        return 0

    def with_return_index(self, index: Union[str, int]):
        """Return a copy of the operation with a new return index."""
        op: LambdaOp = copy(self)
        op.return_index = index
        return op


class LambdaBlock(AbstractBlock):
    @dataclass(eq=True, frozen=True)
    class Signature:
        n_rows: int
        klass: type
        fn: callable
        # dicts are not hashable, so inputs should be a sorted tuple of tuples
        inputs: Tuple[Tuple[Union[str, int], int]]

    @property
    def signature(self) -> Hashable:
        return self.Signature(
            klass=LambdaBlock,
            fn=self.data.fn,
            inputs=tuple(sorted((k, id(v)) for k, v in self.data.inputs.items())),
            nrows=self.data.shape[0],
        )

    def __init__(self, data: LambdaOp):

        self.data = data

    @classmethod
    def from_column_data(cls, data: LambdaOp) -> Tuple[LambdaBlock, BlockView]:
        block_index = data.return_index
        data = data.with_return_index(None)
        block = cls(data=data)
        return BlockView(block=block, block_index=block_index)

    @classmethod
    def from_block_data(cls, data: LambdaOp) -> Tuple[AbstractBlock, BlockView]:
        return cls(data=data)

    @classmethod
    def _consolidate(cls, block_refs: Sequence[BlockRef]) -> BlockRef:
        pass

    def _convert_index(self, index):
        return translate_index(index, length=len(self.data))  # TODO

    def _get(
        self,
        index,
        block_ref: BlockRef,
        indexed_inputs: dict = None,
        materialize: bool = True,
    ) -> Union[BlockRef, dict]:
        if indexed_inputs is None:
            indexed_inputs = {}
        index = self._convert_index(index)

        outputs = self.data._get(
            index=index, indexed_inputs=indexed_inputs, materialize=materialize
        )

        # convert raw outputs into columns
        if isinstance(index, int):
            if materialize:
                return {
                    name: outputs
                    if (col._block_index is None)
                    else outputs[col._block_index]
                    for name, col in block_ref.columns.items()
                }
            else:
                # outputs is a
                return {
                    name: col._create_cell(outputs.with_return_index(col._block_index))
                    for name, col in block_ref.columns.items()
                }

        else:
            if materialize:
                outputs = {
                    name: col.from_data(
                        col.collate(
                            outputs
                            if (col._block_index is None)
                            else outputs[col._block_index]
                        )
                    )
                    for name, col in block_ref.columns.items()
                }
                return [
                    BlockRef(columns={name: col}, block=col._block)
                    for name, col in outputs.items()
                ]
            else:
                block = self.from_block_data(outputs)
                columns = {
                    name: col._clone(
                        data=BlockView(block=block, block_index=col._block_index)
                    )
                    for name, col in block_ref.columns.items()
                }
                return BlockRef(block=block, columns=columns)

    def _get_data(self, index: BlockIndex) -> object:
        return self.data.with_return_index(index)

    def _write_data(self, path: str, *args, **kwargs):

        return super()._write_data(path, *args, **kwargs)

    @staticmethod
    def _read_data(path: str, *args, **kwargs) -> object:
        return super()._read_data(path, *args, **kwargs)
