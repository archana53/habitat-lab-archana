#!/usr/bin/env python3

# Copyright (c) Facebook, Inc. and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from habitat import Config
from habitat.tasks.rearrange.multi_task.logical_expr import LogicalExpr
from habitat.tasks.rearrange.multi_task.pddl_predicate import Predicate
from habitat.tasks.rearrange.multi_task.rearrange_pddl import (
    PddlEntity,
    PddlSimInfo,
    do_entity_lists_match,
    ensure_entity_lists_match,
)
from habitat.tasks.rearrange.multi_task.task_creator_utils import (
    create_task_object,
)
from habitat.tasks.rearrange.rearrange_task import RearrangeTask
from habitat.tasks.rearrange.utils import rearrange_logger


@dataclass
class ActionTaskInfo:
    task_config: Optional[Config]
    task: str
    task_def: str
    config_args: Dict[str, Any] = field(default_factory=dict)
    add_task_args: Dict[str, PddlEntity] = field(default_factory=list)


class PddlAction:
    def __init__(
        self,
        name: str,
        parameters: List[PddlEntity],
        pre_cond: LogicalExpr,
        post_cond: List[Predicate],
        task_info: ActionTaskInfo,
    ):
        """
        :param predicate_lookup_fn: A function that takes as input a predicate
            identifier and returns a predicate if one was found.
        """
        if not isinstance(pre_cond, LogicalExpr):
            raise ValueError(f"Incorrect type {pre_cond}")
        if not isinstance(post_cond, LogicalExpr):
            raise ValueError(f"Incorrect type {pre_cond}")

        self._name = name
        self._params = parameters
        self.name_to_param = {p.name: p for p in self._params}
        self._param_values: Optional[List[PddlEntity]] = None
        self._pre_cond = pre_cond
        self._post_cond = post_cond
        self._task_info = task_info

    def get_arg_value(self, param_name: str) -> Optional[PddlEntity]:
        for param, param_value in zip(self._params, self._param_values):
            if param.name == param_name:
                return param_value
        return None

    @property
    def name(self):
        return self._name

    @property
    def n_args(self):
        return len(self._params)

    def are_args_compatible(self, arg_values: List[PddlEntity]) -> bool:
        return do_entity_lists_match(self._args, arg_values)

    def set_param_values(self, param_values: List[PddlEntity]) -> None:
        ensure_entity_lists_match(self._params, self._param_values)
        self._param_values = param_values

        sub_dict = {
            from_entity: to_entity
            for from_entity, to_entity in zip(self._params, self._param_values)
        }

        # Substitute into the post and pre conditions
        self._param_values = [p.sub_in(sub_dict) for p in self._param_values]

    def clone(self) -> "PddlAction":
        return PddlAction(
            self._name,
            [p.clone() for p in self._params],
            self._pre_cond.clone(),
            [p.clone() for p in self._post_cond],
            self._task_info,
        )

    def apply(self, sim_info: PddlSimInfo) -> None:
        for p in self._post_cond:
            p.set_state(sim_info)

    @property
    def param_values(self):
        if self._param_values is None:
            raise ValueError()
        if len(self._param_values) != len(self._params):
            raise ValueError()
        return self._param_values

    def get_task_kwargs(self, sim_info: PddlSimInfo) -> Dict[str, Any]:
        task_kwargs = {"orig_applied_args": {}}
        for param, param_value in zip(self._params, self.param_values):
            task_kwargs[param.name] = sim_info.search_for_entity(param_value)
            task_kwargs["orig_applied_args"][param.name] = param_value.name
        task_kwargs.update(
            **{
                k: sim_info.search_for_entity(v)
                for k, v in self._task_info.add_task_args.items()
            }
        )
        task_kwargs["task_name"] = self._task_info.task
        return task_kwargs

    def init_task(
        self,
        sim_info: PddlSimInfo,
        should_reset: bool = True,
        add_task_kwargs: Optional[Dict[str, Any]] = None,
    ) -> RearrangeTask:

        rearrange_logger.debug(
            f"Loading task {self._task_info.task} with definition {self._task_info.task_def}"
        )
        if add_task_kwargs is None:
            add_task_kwargs = {}
        task_kwargs = {
            **self.get_task_kwargs(sim_info),
            **add_task_kwargs,
        }
        return create_task_object(
            task_cls_name=self._task_info.task,
            task_config_path=self._task_info.task_def,
            cur_config=self._task_info.task_config,
            cur_env=sim_info.env,
            cur_dataset=sim_info.dataset,
            should_super_reset=should_reset,
            task_kwargs=task_kwargs,
            episode=sim_info.epiosde,
            task_config_args=self._task_info.config_args,
        )
