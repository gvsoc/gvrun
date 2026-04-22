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
import sys
import textwrap
import typing
from dataclasses import fields, is_dataclass, MISSING
from typing import get_type_hints

from gvrun.runtime import is_runtime_annotation, unwrap_annotated


# Fields inherited from Config base class — skip these. ``name`` is intentionally
# kept: it carries the user-visible identifier (e.g. a router mapping name) into
# the generated C++ struct so models can use it without a side channel.
_SKIP_FIELDS = {'parent', 'label', 'path', 'children', 'links', 'defines'}

# Python types we can map to C++
_TYPE_MAP = {
    int:   'int64_t',
    bool:  'bool',
    float: 'double',
    str:   'const char *',
}

# Mapping from C++ type to the corresponding vp::RuntimeFieldType enum name.
_RUNTIME_TYPE_ENUM = {
    'int64_t':      'vp::RUNTIME_INT64',
    'bool':         'vp::RUNTIME_BOOL',
    'double':       'vp::RUNTIME_DOUBLE',
    'const char *': 'vp::RUNTIME_STRING',
}


def _cpp_type(python_type) -> str | None:
    """Map a Python type annotation to its C++ equivalent.

    Unwraps ``Annotated[T, ...]`` before mapping so a field typed as
    ``Annotated[str, Runtime]`` resolves to ``const char *`` the same way
    a bare ``str`` would.
    """
    python_type = unwrap_annotated(python_type)
    if isinstance(python_type, str):
        mapping = {'int': 'int64_t', 'bool': 'bool', 'float': 'double', 'str': 'const char *'}
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
    if cpp_t == 'const char *':
        if value is None:
            return 'nullptr'
        s = str(value).replace('\\', '\\\\').replace('"', '\\"')
        return f'"{s}"'
    return None


def _resolve_forward_ref(ref, owner_cls):
    """Resolve a string forward reference against ``owner_cls``'s module."""
    if not isinstance(ref, str):
        return ref
    module = sys.modules.get(getattr(owner_cls, '__module__', None))
    if module is None:
        return None
    return getattr(module, ref, None)


def _list_elem_dataclass(resolved_type, owner_cls):
    """If ``resolved_type`` is ``list[X]`` with X a dataclass, return X. Else None."""
    origin = typing.get_origin(resolved_type)
    if origin is not list:
        return None
    args = typing.get_args(resolved_type)
    if len(args) != 1:
        return None
    elem = args[0]
    if isinstance(elem, str):
        elem = _resolve_forward_ref(elem, owner_cls)
    if elem is None or not is_dataclass(elem):
        return None
    return elem


def get_config_fields(config_cls):
    """Get the list of packable fields from a Config dataclass.

    Returns a list of dicts. Three flavours of entry are produced:

    * scalar    — ``cpp_type`` is one of int64_t/bool/double/const char *,
                  with ``default`` and ``runtime`` flags.
    * list      — ``cpp_type == 'list'`` with ``list_elem_cls`` pointing at
                  the element dataclass. Generates a (count, pointer) pair
                  in the C++ struct; the array itself is materialised by
                  ``tree_gen``.

    Used by both header generation and tree generation.
    """
    # Resolve PEP 563 string annotations so Annotated[T, Runtime] is a
    # real object (not the string "Annotated[T, Runtime]").
    try:
        type_hints = get_type_hints(config_cls, include_extras=True)
    except Exception:
        type_hints = {}

    result = []
    for f in fields(config_cls):
        if f.name in _SKIP_FIELDS:
            continue
        resolved_type = type_hints.get(f.name, f.type)

        elem_cls = _list_elem_dataclass(resolved_type, config_cls)
        if elem_cls is not None:
            result.append({
                'name': f.name,
                'cpp_type': 'list',
                'list_elem_cls': elem_cls,
                'default': None,
                'runtime': False,
            })
            continue

        cpp_t = _cpp_type(resolved_type)
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
            'runtime': is_runtime_annotation(resolved_type),
        })
    return result


def _header_include_path(config_cls) -> str:
    """Return the canonical ``<subdir>/<snake>.hpp`` path for ``config_cls``.

    Mirrors the layout used by ``runner._generate_config_headers``: the first
    module path component becomes the subdirectory, and the class name is
    snake-cased to form the file stem.
    """
    mod_parts = config_cls.__module__.split('.')
    subdir = mod_parts[0] if len(mod_parts) >= 2 else ''
    snake = re.sub(r'(?<!^)(?=[A-Z])', '_', config_cls.__name__).lower()
    if subdir:
        return f'{subdir}/{snake}.hpp'
    return f'{snake}.hpp'


def runtime_field_enum(cpp_t: str) -> str | None:
    """Return the vp::RuntimeFieldType enumerator name for a C++ type."""
    return _RUNTIME_TYPE_ENUM.get(cpp_t)


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

    # Pull in headers for any nested Config types appearing as list elements.
    nested_includes = []
    for fld in field_list:
        if fld['cpp_type'] == 'list':
            nested_includes.append(_header_include_path(fld['list_elem_cls']))

    lines = []
    lines.append('/*')
    lines.append(f' * Auto-generated from {module_name} — do not edit manually.')
    lines.append(' */')
    lines.append('')
    lines.append('#pragma once')
    lines.append('')
    lines.append('#include <cstddef>')
    lines.append('#include <cstdint>')
    for inc in sorted(set(nested_includes)):
        lines.append(f'#include <{inc}>')
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
        if fld['cpp_type'] == 'list':
            elem_name = fld['list_elem_cls'].__name__
            lines.append(f'    size_t {fld["name"]}_count;')
            lines.append(f'    const {elem_name} *{fld["name"]};')
        else:
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
