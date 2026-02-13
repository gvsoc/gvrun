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

import rich.tree
import rich.table
from typing_extensions import Any

__attribute_arg_values: dict[str,Any] = {}

def set_attributes(attributes: list[str]):
    global __attribute_arg_values

    for prop in attributes:
        key, value = prop.split('=', 1)
        __attribute_arg_values[key] = value


def get_attribute_arg_value(name: str) -> Any:
    return __attribute_arg_values.get(name)

class Attr:
    """
    Parent class for all attributes

    The attributes are the high-level characterics of the hardware system.
    They can for example be memory size, number of cores and so on.
    Attributes are described as a tree of key/value properties.
    The build process will for example be able to know the memory size for each level.

    Attributes
    ----------
    parent (SystemTreeNode | Attr): Parent owning this attributes. Can be a system tree
        node for the top attribute or an attribute for the others
    name (str | None): Name of the attribute. Can be None for the top attribute.
    allowed_values (list[Any] | None=None): List of allowed values or None if any value is allowed
    description (str): Description of the attribute
    cast (Type[Any] | None=None): If it is not None, cast the value to the specified type
    """
    def __init__(self, parent: "SystemTreeNode | Attr", name: str | None,
            allowed_values: list[Any] | None=None, description: str='',
            cast: type | None=None):
        self._name = name
        self._parent = parent
        self._path = name
        self._childs = []
        self._allowed_values = allowed_values
        self._description = description
        self._cast = cast

        paths = []
        if parent is not None:
            if isinstance(parent, Attr):
                parent._childs.append(self)
            parent_path = parent.get_path()
            if parent_path is not None and parent_path != '':
                paths.append(parent_path)

        if name is not None:
            paths.append(name)

        self._path = '/'.join(paths)

    def get_path(self):
        """Return the attribute path.

        The path is the concatenation of the names of all parents of this attribute, separated
        by '/', and including both attribute parents and system tree node parents.

        Parameters
        ----------
        target : str
            Name of the target. The name must corresponds to a python module.

        Returns
        -------
        str: The attribute path
        """
        return self._path

    def __getattribute__(self, name):
        """Override the default __getattribute__ to allow getting attribute value with just the
        name"""
        if name[0] == '_':
            return object.__getattribute__(self, name)
        attr = object.__getattribute__(self, name)
        if isinstance(attr, Value):
            return attr.value
        return attr


class Value(Attr):
    """
    Value attribute

    This attribute can be used to store a single value.
    It can not have any child.

    Attributes
    ----------
    parent (SystemTreeNode | Attr): Parent owning this attributes. Can be a system tree
        node for the top attribute or an attribute for the others
    name (str): Name of the attribute.
    value (Any): Value of the attribute.
    allowed_values (list[Any] | None=None): List of allowed values or None if any value is allowed
    description (str): Description of the attribute
    cast (Type[Any] | None=None): If it is not None, cast the value to the specified type
    """
    def __init__(self, parent: "SystemTreeNode | Attr", name: str, value: Any,
            allowed_values: list[Any] | None=None, description: str='',
            cast: type | None=None):
        super().__init__(parent, name, allowed_values, description, cast)
        self.value = value
        arg_value = get_attribute_arg_value(self._path)
        if arg_value is not None:
            self.value = arg_value

        if self._allowed_values is not None:
            if self.value not in self._allowed_values:
                raise RuntimeError(f'Trying to set attribute to invalid value '
                    f'(name: {self.get_path()}, value: {self.value}, '
                    f'allowed_values: {", ".join(self._allowed_values)})')

        if self._cast is not None:
            if self._cast == int:
                if isinstance(value, str):
                    self.value = int(self.value, 0)
                else:
                    self.value = int(self.value)


class Area(Attr):
    """
    Area attribute

    This attribute can be used to store an address range through a base address and a size.
    It can not have any child.

    Attributes
    ----------
    parent (SystemTreeNode | Attr): Parent owning this attributes. Can be a system tree
        node for the top attribute or an attribute for the others
    name (str): Name of the attribute.
    base (int): Base address of the area.
    size (int): Size of the area.
    description (str): Description of the attribute
    """
    def __init__(self, parent: "SystemTreeNode | Attr", name: str, base: int,
            size: int, description=''):
        super().__init__(parent, name, description=description)
        self.base = Value(self, f'base', base, cast=int)
        self.size = Value(self, f'size', size, cast=int)


class Tree(Attr):
    """
    Tree attribute

    This attribute can be used to store a tree of attributes.
    It is usefull when a hierarchy of attributes is needed.

    Attributes
    ----------
    parent (SystemTreeNode | Attr): Parent owning this attributes. Can be a system tree
        node for the top attribute or an attribute for the others
    name (str | None): Name of the attribute. Can be None for the top tree attribute.
    """
    def __init__(self, parent: "SystemTreeNode | Attr | None", name: str | None=None):
        super().__init__(parent, name)

    def _dump_attributes(self, tree: rich.tree.Tree):
        """Dump the whole hierarchy of attributes to the tree"""
        if self._name is not None:
            tree = tree.add(self._name)

        table = None
        for child in self._childs:
            if isinstance(child, Value) or isinstance(child, Area):
                if table is None:
                    table = rich.table.Table()
                    table.add_column('Name')
                    table.add_column('Value')
                    table.add_column('Full name')
                    table.add_column('Allowed values')
                    table.add_column('Description')
                    tree.add(table)

                if child._allowed_values is None:
                    if child._cast == int:
                        allowed_values = 'any integer'
                    else:
                        allowed_values = 'any string'
                else:
                    allowed_values = ', '.join(child._allowed_values)

                if isinstance(child, Value):
                    table.add_row(child._name, str(child.value), child.get_path(), allowed_values, child._description)
                else:
                    table.add_row(child._name, f'{child.base:#x}, {child.size:#x}', f'{child.get_path()}/{{base|size}}', '(int, int)', child._description)

            else:
                child._dump_attributes(tree)
