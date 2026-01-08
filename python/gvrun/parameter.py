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

from typing_extensions import Any, List, Tuple


__cmdline_parameter_values = {}
__node_parameter_values = {}

def set_parameters(parameters):
    global __cmdline_parameter_values

    for prop in parameters:
        key, value = prop.split('=', 1)
        __cmdline_parameter_values[key] = value

def set_parameters_from_node(parameters: List[Tuple[str,Any]]):
    global __node_parameter_values

    for prop in parameters:
        __node_parameter_values[prop[0]] = prop[1]

def get_parameter_arg_value(name):
    # First return the value from command_line arguments as it overwrite the ones from the nodes
    value = __cmdline_parameter_values.get(name)
    if value is not None:
        return value
    # If not set, return from nodes
    return __node_parameter_values.get(name)


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
        if self.cast is None and value is not None:
            # Cast to the type of desc.value when desc.cast is None
            self.cast = type(value)


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
