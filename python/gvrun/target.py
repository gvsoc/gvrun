#
# Copyright (C) 2025 Germain Haugou
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

#
# Authors: Germain Haugou (germain.haugou@gmail.com)
#

import argparse
import importlib
import inspect
from typing_extensions import Any, Callable, Dict
from gvrun.systree import SystemTreeNode
from gvrun.attribute import Tree
from gvrun.parameter import BuildParameter, Parameter, get_parameter_arg_value
from abc import ABC, abstractmethod


def get_target(target: str) -> 'type[Target]':
    """Return the class implementing the support for the specified target.

    The target is specified as a python module which is imported from python path.
    It returns the class 'Target' from the imported module.

    Parameters
    ----------
    target : str
        Name of the target. The name must corresponds to a python module.

    Returns
    -------
    class
        The class 'Target' of the imported module.
    """
    try:
        module = importlib.import_module(target)

    except ModuleNotFoundError as exc:
        if exc.name == target:
            raise RuntimeError(f'Invalid target specified: {target}') from exc

        raise RuntimeError(f"Dependency '{exc.name}' of the target module '{target}' is"
            " missing (add --py-stack for more information).") from exc

    if 'Target' in dir(module):

        target_class = getattr(module, 'Target', None)

        # Check that the class comes from the module itself and not from an imported one
        if inspect.isclass(target_class) and target_class.__module__ == module.__name__:
            return target_class

    raise RuntimeError(f'Could not find any gvrun Target class in target: {target}')


class Target(SystemTreeNode):
    """
    Parent class for the target

    The target is the entry point class describing the whole system.
    This can be a simple system like a board or a more complex one like a multi-board system.
    Any target must inherit this class.

    Attributes
    ----------
    parser (argparse.ArgumentParser): Argument parser
    name (str | None): Name of the target.
    """
    def __init__(self, parser: argparse.ArgumentParser, name: str | None):
        super().__init__(name)
        self.__parser = parser
        self._set_node_type('Target')

    def _process_and_dump_tree(self, inc_arch: bool, inc_build: bool, inc_target: bool,
        inc_attr: bool, inc_prop: bool):
        """Dump the tree whole child hierarchy of the target"""
        self._process_has_tree_content(inc_arch, inc_build, inc_target, inc_attr, inc_prop)
        super()._dump_tree(None, inc_arch, inc_build, inc_target, inc_attr, inc_prop)
