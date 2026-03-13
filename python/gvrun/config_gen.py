#
# Copyright (C) 2026 ETH Zurich and University of Bologna
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

"""
Generate C++ config struct headers from Python Config dataclasses.

Generated structs are plain aggregates — no base class, no methods.
They support aggregate initialization:

    constexpr MemoryConfig cfg{65536, false, 0};

Usage:
    from config_gen import generate_cpp_header
    from memory.memory_config import MemoryConfig
    generate_cpp_header(MemoryConfig, output_path='memory_config.hpp')
"""

from __future__ import annotations
import os
import re
import textwrap
from dataclasses import fields, is_dataclass, MISSING


# Fields inherited from Config base class — skip these
_SKIP_FIELDS = {'parent', 'name', 'path'}

# Python types we can map to C++
_TYPE_MAP = {
    int:   'int64_t',
    bool:  'bool',
    float: 'double',
}


def _cpp_type(python_type) -> str | None:
    """Map a Python type annotation to its C++ equivalent."""
    if isinstance(python_type, str):
        mapping = {'int': 'int64_t', 'bool': 'bool', 'float': 'double'}
        return mapping.get(python_type)
    return _TYPE_MAP.get(python_type)


def _cpp_default(value, cpp_t: str) -> str:
    """Format a Python default value as a C++ literal."""
    if cpp_t == 'bool':
        return 'true' if value else 'false'
    if cpp_t == 'double':
        return repr(float(value))
    if cpp_t == 'int64_t':
        if isinstance(value, str):
            return str(int(value.strip().rstrip(','), 0))
        return str(int(value))
    return None


def get_config_fields(config_cls):
    """Get the list of packable fields from a Config dataclass.

    Returns a list of dicts with keys: name, cpp_type, default.
    Used by both header generation and tree generation.
    """
    result = []
    for f in fields(config_cls):
        if f.name in _SKIP_FIELDS:
            continue
        cpp_t = _cpp_type(f.type)
        if cpp_t is None:
            continue

        default_val = None
        if f.default is not MISSING:
            default_val = f.default
        elif f.default_factory is not MISSING:
            default_val = f.default_factory()

        result.append({
            'name': f.name,
            'cpp_type': cpp_t,
            'default': default_val,
        })
    return result


def cpp_value(value, cpp_t: str) -> str:
    """Format a Python value as a C++ literal. Public for use by tree generator."""
    return _cpp_default(value, cpp_t)


def generate_cpp_header(config_cls, output_path: str = None) -> str:
    """
    Generate a C++ header with a plain aggregate config struct.

    Parameters
    ----------
    config_cls : type
        A dataclass (typically inheriting from gvrun.config.Config).
    output_path : str, optional
        If given, write the header to this file path.

    Returns
    -------
    str
        The generated C++ header content.
    """
    if not is_dataclass(config_cls):
        raise TypeError(f'{config_cls} is not a dataclass')

    class_name = config_cls.__name__
    module_name = config_cls.__module__

    field_list = get_config_fields(config_cls)

    # Build docstring from the Python class
    docstring = config_cls.__doc__ or f'Configuration struct for {class_name}.'
    docstring = textwrap.dedent(docstring).strip()

    lines = []
    lines.append('/*')
    lines.append(f' * Auto-generated from {module_name} — do not edit manually.')
    lines.append(' */')
    lines.append('')
    lines.append('#pragma once')
    lines.append('')
    lines.append('#include <cstdint>')
    lines.append('')

    # Docblock
    lines.append('/**')
    for doc_line in docstring.split('\n'):
        lines.append(f' * {doc_line}')
    lines.append(' */')

    lines.append(f'struct {class_name}')
    lines.append('{')

    # No default member initializers — keeps the struct trivially
    # default-constructible so that C++ member initialization doesn't
    # overwrite data written by the base class template constructor.
    for fld in field_list:
        lines.append(f'    {fld["cpp_type"]} {fld["name"]};')

    lines.append('};')
    lines.append('')

    content = '\n'.join(lines)

    if output_path:
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
        with open(output_path, 'w') as fp:
            fp.write(content)
        print(f'Generated {output_path}')

    return content
