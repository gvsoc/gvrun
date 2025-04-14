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


import importlib
import inspect
import rich.table
import traceback
import gvrun.commands
from abc import ABC, abstractmethod

def get_target(target: str) -> 'Target':
    """Returns the class implementing the support for the specified target.

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

    raise RuntimeError(f'Could not find any Gapy Target class in target: {target}')


class BinaryLoader(ABC):

    @abstractmethod
    def register_binary(self, binary):
        pass

class SystemTreeNode:

    def __init__(self, name, parent=None):
        self.name = name
        self.childs = []
        self.build_properties = {}
        self.target_properties = {}
        self.target_properties_values = {}
        self.executables = []
        self.parent = parent
        self.binary_loaders = []
        if parent is not None:
            self.path = f'{parent.get_path()}/{name}'
            parent.childs.append(self)
        else:
            self.path = f'{name}'

    def target_prepare(self):
        pass

    def target_prepare_walk(self):
        for child in self.childs:
            child.target_walk()

        self.target_prepare_walk()

    def target_gen(self):
        pass

    def target_gen_walk(self):
        for child in self.childs:
            child.target_gen_walk()

        self.target_gen()

    def configure_after_compile(self):
        pass

    def configure_after_compile_all(self):
        for child in self.childs:
            child.configure_after_compile_all()

        self.configure_after_compile()

    def add_binary_loader(self, loader):
        self.binary_loaders.append(loader)

    def dump_flash_layout(self, layout_level):
        pass

    def dump_flash_layout_walk(self, layout_level):
        for child in self.childs:
            child.dump_flash_layout_walk(layout_level)

        self.dump_flash_layout(layout_level)


    def get_property(self, name):
        return None

    def get_path(self):
        return self.path

    def _dump_level_build_properties(self, tree):
        if len(self.build_properties.values()) != 0:
            table = rich.table.Table(title='Properties')

            table.add_column('Name')
            table.add_column('Value')
            table.add_column('Description')

            for name, value in self.build_properties.items():
                path = f'{self.get_path()}/{value.name}'
                table.add_row(path, str(value.value), value.description)

            tree.add(table)

    def has_build_properties(self):

        for child in self.childs:
            if child.has_build_properties():
                return True

        return False

    def dump_build_properties(self, tree):
        tree = tree.add(f'{self.name}')
        self._dump_level_build_properties(tree)

        for component in self.childs:
            component.dump_build_properties(tree)

    def declare_target_property(self, descriptor):

        if self.target_properties.get(descriptor.name) is not None:
            traceback.print_stack()
            raise RuntimeError(f'Property {descriptor.name} already declared')

        self.target_properties[descriptor.name] = descriptor

        arg = gvrun.commands.get_target_property(descriptor.full_name)
        if arg is None:
            arg = self.target_properties_values.get(descriptor.name)
        if arg is not None:
            if descriptor.allowed_values is not None:
                if arg not in descriptor.allowed_values:
                    raise RuntimeError(f'Trying to set target property to invalid value '
                        f'(name: {descriptor.full_name}, value: {arg}, '
                        f'allowed_values: {", ".join(descriptor.allowed_values)})')

            if descriptor.cast is not None:
                if descriptor.cast == int:
                    if isinstance(arg, str):
                        arg = int(arg, 0)
                    else:
                        arg = int(arg)

            descriptor.value = arg

    def has_target_properties(self):
        if len(self.target_properties) != 0:
            return True

        for child in self.childs:
            if child.has_target_properties():
                return True

        return False

    def dump_level_target_properties(self, tree):

        if self.name is None or not self.has_target_properties():
            subtree = tree
        else:
            subtree = tree.add(self.name)

        if len(self.target_properties) > 0:
            table = rich.table.Table(title='Properties')
            table.add_column('Name')
            table.add_column('Value')
            table.add_column('Full name')
            table.add_column('Allowed values')
            table.add_column('Description')

            for prop_name, prop in self.target_properties.items():
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

            subtree.add(table)

        for component in self.childs:
            component.dump_level_target_properties(subtree)

    def add_executable(self, executable):
        self.executables.append(executable)

        for loader in self.binary_loaders:
            loader.register_binary(executable.binary)

    def get_executables(self):
        executables = []
        executables += self.executables
        if self.parent is not None:
            executables += self.parent.get_executables()

        return executables


    def set_target_property(self, name: str, value):
        if name.find('/') != -1:
            comp, prop_name = name.split('/', 1)
            return self.get_component(comp).set_target_property(prop_name, value)

        if self.target_properties.get(name) is None:
            self.target_properties_values[name] = value
        else:
            self.target_properties[name].value = value



    def get_target_property(self, name: str, path: str=None) -> any:
        """Return the value of a target property.

        This can be called to get the value of a target property.

        Parameters
        ----------
        name : str
            Name of the property

        path : str
            Give the path of the component owning the property. If it is not None, the path is
            added as a prefix to the property name.

        Returns
        -------
        str
            The property value.
        """

        if name.find('/') != -1:
            comp, prop_name = name.split('/', 1)
            print ('%s %s' % (comp, prop_name))
            return self.get_component(comp).get_target_property(prop_name)

        # if path is not None:
        #     name = path + '/' + name
        if self.target_properties.get(name) is None:
            raise RuntimeError(f'Trying to get undefined property: {name}')

        prop = self.target_properties.get(name)
        value = prop.value

        return value


class BuildProperty():

    def __init__(self, name, value, description, path):
        self.name = name
        self.value = value
        self.description = description
        self.path = path

class Component(SystemTreeNode):

    def __init__(self, name, target_name=None, parent=None):
        super().__init__(name, parent)
        self.path = None
        self.target_name = target_name

    def get_target_name(self):
        return self.target_name

    def get_property_from_root(self, name):
        if self.parent is not None:
            return self.parent.get_property_from_root(name)
        return self.get_build_property(name).value

    def get_build_property(self, name):
        if name[0] == '/':
            return self.get_property_from_root(name[1:])
        else:
            return self.build_properties.get(name).value

    def set_build_property(self, name, value):
        self.build_properties.get(name).value = value

    def has_build_properties(self):
        if len(self.executables) != 0:
            return False

        return super().has_build_properties()

    def dump_build_properties(self, tree):

        if self.target_name is not None:
            tree = tree.add(f'Component({self.name})')
            self._dump_level_build_properties(tree)

            for component in self.childs:
                component.dump_build_properties(tree)

    def declare_property(self, name, value, description):
        if self.path is not None:
            path = f'{self.path}/{name}'
        else:
            path = name

        user_value = gvrun.commands.get_user_property(path)
        if user_value is not None:

            if isinstance(value, bool):
                if isinstance(user_value, bool):
                    value = user_value
                else:
                    value = user_value in ['True', 'true']
            elif isinstance(value, int):
                value = int(user_value)
            elif isinstance(value, list) and not isinstance(user_value, list):
                value = [ user_value ]
            else:
                value = user_value

        self.build_properties[name] = BuildProperty(name, value, description, path)
        return value

    def build(self, builder, builddir):
        for child in self.childs:
            child.build(builder, builddir)


class Target(SystemTreeNode):

    def __init__(self, name, parser):
        super().__init__(name)
        self.parser = parser

    def dump_target_properties(self):

        tree = rich.tree.Tree('Properties')

        self.dump_level_target_properties(tree)

        rich.print (tree)


class Property():
    """
    Placeholder for target properties.

    Attributes
    ----------
    name : str
        Name of the property.
    path : str
        Path of the property in the target hierarchy.
    value : any
        Value of the property.
    description : str
        Description of the property.
    path : str
        Path in the target of the property.
    cast : type
        When the property is overwritten from command-line, cast it to the specified type.
    dump_format : str
        When the property is dumped, dump it wth the specified format
    allowed_values : list
        List of allowed values. If set to None, anything is allowed.
    """

    def __init__(self, name: str, value: any, description: str, path: str=None,
            allowed_values: list=None, cast: type=None, dump_format: str=None):

        self.name = name
        self.path = path
        if path is not None:
            self.full_name = path + '/' + name
        else:
            self.full_name = name
        self.description = description
        self.value = value
        self.allowed_values = allowed_values
        self.cast = cast
        self.format = dump_format
