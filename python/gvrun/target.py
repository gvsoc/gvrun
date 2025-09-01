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
import abc
import importlib
import inspect
from typing_extensions import Any, Callable, Dict
import rich.table
import rich.tree
import traceback
import gvrun.commands
import gvrun.attribute
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


class Executable(object, metaclass=abc.ABCMeta):
    """ Interface class for executable classes
    """
    @abc.abstractmethod
    def get_binary(self) -> str:
        """
        Return the filesystem path of the binary for this executable.

        Returns:
            str: Path to the binary
        """
        ...


class Parameter():
    """
    Placeholder for target parameters.

    Attributes
    ----------
    name : str
        Name of the parameter.
    path : str
        Path of the parameter in the target hierarchy.
    value : any
        Value of the parameter.
    description : str
        Description of the parameter.
    path : str
        Path in the target of the parameter.
    cast : type
        When the parameter is overwritten from command-line, cast it to the specified type.
    dump_format : str
        When the parameter is dumped, dump it wth the specified format
    allowed_values : list
        List of allowed values. If set to None, anything is allowed.
    """

    def __init__(self, name: str, value: Any, description: str, path: str | None=None,
            allowed_values: list | None=None, cast: type | None=None, dump_format: str | None=None,
            is_target=False, is_arch=False, is_build=False):

        self.name = name
        self.path = path
        if path is not None and path != '':
            self.full_name = path + '/' + name
        else:
            self.full_name = name

        self.description = description
        self.value = value
        self.allowed_values = allowed_values
        self.cast = cast
        self.format = dump_format
        self.is_target = is_target
        self.is_arch = is_arch
        self.is_build = is_build

    def get_value(self):
        return self.value

class TargetParameter(Parameter):

    def __init__(self, parent, name: str, value: Any, description: str,
            allowed_values: list | None=None, cast: type | None=None, dump_format: str | None=None):

        super().__init__(name=name, value=value, description=description, path=parent.get_path(),
            allowed_values=allowed_values, cast=cast, dump_format=dump_format, is_target=True)

        parent._declare_parameter(self)


class BuildParameter(Parameter):

    def __init__(self, parent, name: str, value: Any, description: str,
            allowed_values: list | None=None, cast: type | None=None, dump_format: str | None=None):

        super().__init__(name=name, value=value, description=description, path=parent.get_path(),
            allowed_values=allowed_values, cast=cast, dump_format=dump_format, is_build=True)

        parent._declare_parameter(self)


class ArchParameter(Parameter):

    def __init__(self, parent, name: str, value: Any, description: str,
            allowed_values: list | None=None, cast: type | None=None, dump_format: str | None=None):

        super().__init__(name=name, value=value, description=description, path=parent.get_path(),
            allowed_values=allowed_values, cast=cast, dump_format=dump_format, is_arch=True)

        parent._declare_parameter(self)


class SystemTreeNode:
    """
    Common type for the system tree nodes

    The system tree describes the system to be simulated. It can contain various kinds of nodes,
    such as the target, the architecture omponents or the build process nodes.
    All these types share this class as common parent.
    It provides features for declaring all kinds of parameters (arch, target and build).

    Attributes
    ----------
    name (str): Name of the node.
    parent (SystemTreeNode | None): Parent of this node, can be None if it has no parent, only
        for the top node.
    """

    def __init__(self, name: str | None, parent: "SystemTreeNode | None"=None):
        self.__name = name
        self.__childs = []
        self.__childs_from_name = {}
        self.__parameters = {}
        self.__arch_parameters = {}
        self.__build_parameters = {}
        self.__target_parameters = {}
        self.__executables = []
        self.__parent = parent
        self.__binary_handlers = []
        self.__has_tree_content = False
        self.__attributes = None
        self.__node_type = 'Component'
        self.__target_name = None

        paths = []

        if parent is not None:
            parent_path = parent.get_path()
            if parent_path is not None and parent_path != '':
                paths.append(parent_path)

            parent.__childs.append(self)
            parent.__childs_from_name[name] = self

        if name is not None:
            paths.append(name)

        self.__path = '/'.join(paths)

    def set_target_name(self, name: str):
        """Set target name.

        In case this part of the system tree needs to refered by other tools, such as the build
        process, a target name can be attached with this method.
        The build process will for example use this information to know how to compile an
        executable for this node.
        For simple systems, a single executable is needed and thus a target name must be attached
        only at the top-most node.
        For more complex systems which need severall executables because they aggregate together
        several simple systems (like a multi-board system), one target name must be attached to
        each simple system, so that all the executables can be built. This naturally happens
        when simple systems are aggregated if they already have a target name, which is the case
        if they also used stand-alone.

        Parameters
        ----------
        name (str): The target name.
        """
        self.__target_name = name

    def get_target_name(self) -> str | None:
        """Get target name.

        The target name should be attached to any node which can be executed stand-alone.
        This is used for example by the build process to know how to compile the executable for
        this node

        Returns
        -------
        str | None : The target name or None, if no target name was attached.
        """
        return self.__target_name

    def get_parameter(self, name: str) -> str | None:
        """Get parameter values.

        Parameters are declared when building the system tree. They can be assigned default values
        which can be overwritten by the command line.
        This method can be called to get the value of a parameter.
        The name is relative to this node and allow reaching parameters of its child hierarchy.
        In this case, childs are separated by '/' like in this example: child1/child2/property_name.
        The name can starts with '/' to get the property from the top like in this example:
        /top_comp/child1/property_value.

        Parameters
        ----------
        name (str): The property name.

        Returns
        -------
        str | None : The property value, or None if it is not found.
        """
        if name[0] == '/':
            desc = self.__get_top_parameter(name[1:])
        else:
            desc = self.__get_parameter(name)
        if desc is not None:
            return desc.value
        return None

    def set_parameter(self, name: str, value: Any):
        """Set parameter value.

        Parameters are declared when building the system tree. They can be assigned default values
        which can be overwritten by the command line.
        This method can be called to overwrites the value of a parameter. This will overwrite
        both the default value and the command-line value.
        The name is relative to this node and allow reaching parameters of its child hierarchy.
        In this case, childs are separated by '/' like in this example: child1/child2/property_name.
        The name can starts with '/' to get the property from the top like in this example:
        /top_comp/child1/property_value.

        Parameters
        ----------
        name (str): The parameter name.
        value (Any): The parameter value.
        """
        self.__set_parameter(name, value)

    def set_attributes(self, attributes: gvrun.attribute.Tree):
        """Set the attributes of this node.

        The attributes are the high-level characterics of the hardware system.
        They can for example be memory size, number of cores and so on.
        Attributes are described as a tree of key/value properties.
        Setting the attributes will allow all the tools to query about the architecture.
        The build process will for example be able to know the memory size for each level.

        Parameters
        ----------
        attributes (gvrun.attribute.Tree): The tree of attributes
        """
        self.__attributes = attributes
        return attributes

    def get_attributes(self) -> gvrun.attribute.Tree | None:
        """Get the attributes of this node.

        The attributes are the high-level characterics of the hardware system.
        They can for example be memory size, number of cores and so on.
        Attributes are described as a tree of key/value properties.
        The build process will for example be able to know the memory size for each level.

        Returns
        -------
        gvrun.attribute.Tree | None : The attributes or None if no attribute was assigned.
        """
        return self.__attributes

    def get_child(self, name: str) -> "SystemTreeNode | None":
        """Get a child from his name.

        The tree of nodes is organized based on each node name.
        This node references his childs using their names.

        Returns
        -------
        SystemTreeNode | None : The child or None if no child of this name was found.
        """
        return self.__childs_from_name.get(name)

    def register_binary_handler(self, handler: Callable[[str], None]):
        """Register a binary handler.

        This allow getting notified when an executable is registered, so that it is taken into
        account, for example for configuring an ELF loader in the platform.
        The provided callback will be called for any executable which is registered in this node
        or parent nodes.

        Parameters
        ----------
        handler (Callable[[str]]): The callback to be called when an executable is registered
        """
        self.__binary_handlers.append(handler)

    def get_name(self) -> str | None:
        """Get the name of this node

        The name is defined when the node is instantiated. Some nodes like the top one may not have
        a name.

        Returns
        -------
        str | None : The node name or None if it has no name.
        """
        return self.__name

    def get_path(self, child_path: str | None=None) -> str:
        """Get the node path

        The node path is the concatenation of his name and all his parents names, separated by '/'.
        The top-most parent’s name appears on the left, and this node’s name appears on the right.
        The path is '' if no name is found neither in this node nor in his parents.
        If provided, the additional path is appended to the end.

        Parameters
        ----------
        child_path (str | None): Additional path appended to the end

        Returns
        -------
        str: The node path with the additional path appended to the end
        """
        path = self.__path
        if child_path is not None:
            path = f'{path}/{child_path}'

        return path

    def get_executables(self) -> list[Executable]:
        """Get executables

        This returns all the executables which has been attached to this node and all its childs.

        Returns
        -------
        list[Component]: The list of executables
        """
        executables = []
        executables += self.__executables
        if self.__parent is not None:
            executables += self.__parent.get_executables()

        return executables

    def _add_executable(self, executable: Executable):
        """Add an executable to this node. This will notify any registered binary handler"""
        self.__executables.append(executable)
        self.__notify_binary_handlers(executable)

    def _get_childs(self) -> "list[SystemTreeNode]":
        """Get all childs"""
        return self.__childs

    def _get_parent(self) -> "SystemTreeNode | None":
        """Get parent"""
        return self.__parent

    def _dump_parameter_title(self, name: str | None, type_name: str, class_name: str) -> str:
        """Returns a title for this node suitable for tree dumping"""
        title = f'[cyan]{type_name}[/]([bold magenta]{class_name}[/])'
        if name is not None:
            title = f'[bold magenta]{name}[/]: ' + title
        return title

    def _dump_tree_properties(self, tree: rich.tree.Tree):
        """Dump the tree of properties. By default empty, implemented by GVSOC nodes to dump
        GVSOC model properties"""
        pass

    def _process_has_tree_property(self) -> bool:
        """Tell if this node has properties. Overriden by GVSOC nodes"""
        return False

    def _has_tree_content(self) -> bool:
        """Tell if this node has parameters"""
        return self.__has_tree_content

    def _dump_node_parameters(self, tree: rich.tree.Tree, inc_arch: bool, inc_build: bool,
            inc_target: bool, inc_attr: bool, inc_prop: bool):
        """Dump the parameters, attributes and properties for this node"""
        if inc_attr:
            attr = self.get_attributes()
            if attr is not None:
                sub_tree = tree.add(f'[yellow italic]Attributes[/]')
                attr._dump_attributes(sub_tree)
        if inc_arch and len(self.__arch_parameters) > 0:
            self.__dump_tree_parameter_table(tree, 'Arch', self.__arch_parameters)
        if inc_build and len(self.__build_parameters) > 0:
            self.__dump_tree_parameter_table(tree, 'Build', self.__build_parameters)
        if inc_target and len(self.__target_parameters) > 0:
            self.__dump_tree_parameter_table(tree, 'Target', self.__target_parameters)
        if inc_prop:
            self._dump_tree_properties(tree)

    def _process_has_tree_content(self, inc_arch: bool, inc_build: bool, inc_target: bool,
            inc_attr: bool, inc_prop: bool) -> bool:
        """Determine for the whole hierarchy of this node, if it has parameters, attributes,
        or properties to be displayed, when the tree is dumped. Return True if this node has
        something to display"""
        self.__has_tree_content = inc_arch and len(self.__arch_parameters) > 0 or \
            inc_build and len(self.__build_parameters) > 0 or \
            inc_target and len(self.__target_parameters) > 0 or \
            inc_attr and self.get_attributes() != None or \
            inc_prop and self._process_has_tree_property()

        for child in self.__childs:
            if child._process_has_tree_content(inc_arch, inc_build, inc_target, inc_attr, inc_prop):
                self.__has_tree_content = True

        return self.__has_tree_content

    def _declare_parameter(self, descriptor: Parameter) -> Any:
        """Declare a parameter and return its value"""

        if self.__parameters.get(descriptor.name) is not None:
            traceback.print_stack()
            raise RuntimeError(f'parameter {descriptor.name} already declared')

        self.__parameters[descriptor.name] = descriptor
        if descriptor.is_arch:
            self.__arch_parameters[descriptor.name] = descriptor
        if descriptor.is_build:
            self.__build_parameters[descriptor.name] = descriptor
        if descriptor.is_target:
            self.__target_parameters[descriptor.name] = descriptor


        value = gvrun.commands.get_parameter_arg_value(descriptor.full_name)
        if value is None:
            value = descriptor.value

        self.__set_parameter(descriptor.name, value)

        return value

    def __get_top_parameter(self, name: str) -> Parameter | None:
        """Get a parameter from the top"""
        prop = self.__get_parameter(name, check=False)
        if prop is not None:
            return prop
        if self.__parent is not None:
            return self.__parent.__get_top_parameter(name)
        return None

    def __get_parameter(self, name: str, check: bool=True) -> Parameter | None:
        """Get a parameter"""
        if name.find('/') != -1:
            desc = None
            comp_name, prop_name = name.split('/', 1)
            comp = self.get_child(comp_name)
            if comp is not None:
                desc = comp.__get_parameter(prop_name)
        else:
            desc = self.__parameters.get(name)
        if check and desc is None:
            raise RuntimeError(f'Trying to get invalid parameter (name: {name}')

        return desc

    def __set_parameter(self, name: str, value: Any):
        """Get a parameter value. This will check if the value fits the allowed values and may
        cast the value if specified when declaring the parameter"""
        desc = self.__get_parameter(name)
        if desc is None:
            raise RuntimeError(f'Trying to set invalid parameter (name: {name})')

        if desc.allowed_values is not None:
            if value not in desc.allowed_values:
                raise RuntimeError(f'Trying to set parameter to invalid value '
                    f'(name: {desc.full_name}, value: {value}, '
                    f'allowed_values: {", ".join(desc.allowed_values)})')

        if desc.cast is not None:
            if desc.cast == int:
                if isinstance(value, str):
                    value = int(value, 0)
                else:
                    value = int(value)

        desc.value = value

    def __dump_tree_parameter_table(self, tree: rich.tree.Tree, name: str,
            parameters: Dict[str, Parameter]):
        """Dump the parameters of one kind for this node into a table"""
        table = rich.table.Table(title=f'[yellow]{name} parameters[/]', title_justify="left")
        table.add_column('Name')
        table.add_column('Value')
        table.add_column('Full name')
        table.add_column('Allowed values')
        table.add_column('Description')

        for prop_name, prop in parameters.items():
            prop_full_name = prop.full_name
            value_str = prop.value
            if prop.format is not None:
                value_str = prop.format % prop.value
            value_str = str(value_str)

            if prop.allowed_values is None:
                if prop.cast == int:
                    allowed_values = 'any integer'
                else:
                    allowed_values = 'any string'
            else:
                allowed_values = ', '.join(prop.allowed_values)

            table.add_row(prop_name, value_str, prop_full_name, allowed_values, prop.description)

        tree.add(table)

    def __notify_binary_handlers(self, executable: Executable):
        """Notify a new executable to all callbacks registered in the child hierarchy of this node"""
        for child in self.__childs:
            child.__notify_binary_handlers(executable)

        for handler in self.__binary_handlers:
            handler(executable.get_binary())

    def _set_node_type(self, node_type: str):
        """Set the node type to be displayed when dumping the tree"""
        self.__node_type = node_type

    def _dump_tree(self, tree: rich.tree.Tree | None, inc_arch: bool, inc_build: bool,
            inc_target: bool, inc_attr: bool, inc_prop: bool):
        """Dump the tree whole child hierarchy of this node"""
        new_tree = tree
        if new_tree is None:
            new_tree = rich.tree.Tree(self._dump_parameter_title(self.get_name(), 'Target', self.__class__.__name__))

        if self._has_tree_content():
            if tree is not None:
                new_tree = tree.add(self._dump_parameter_title(self.get_name(), self.__node_type,
                    self.__class__.__name__))
            self._dump_node_parameters(new_tree, inc_arch, inc_build, inc_target, inc_attr, inc_prop)

            for component in self._get_childs():
                component._dump_tree(new_tree, inc_arch, inc_build, inc_target, inc_attr, inc_prop)

        if tree is None:
            rich.print(new_tree)

    def _compile(self, builder: gvrun.commands.Builder, builddir: str):
        """Compile step, should be overriden by build process nodes"""
        pass

    def _compile_all(self, builder: gvrun.commands.Builder, builddir: str):
        """Call the compile step for every node of the child hierarchy"""
        for child in self._get_childs():
            child._compile_all(builder, builddir)

        self._compile(builder, builddir)


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
