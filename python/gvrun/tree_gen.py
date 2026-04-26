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
Generate a per-target C++ file containing the compiled component tree.

The generated file contains:
  - constexpr config instances for each component that has a Python Config
  - Binding arrays for each component
  - A tree of ComponentTreeNode describing the component hierarchy,
    including vp_component module names and bindings
  - An extern "C" entry point vp_get_platform_tree() returning the root

Called during cmake configure time by the gapy 'components' command.
"""

from __future__ import annotations
import hashlib
import os
import re
from dataclasses import fields, is_dataclass


# Reuse field helpers from config_gen
from gvrun.config_gen import (
    _SKIP_FIELDS,
    _header_include_path,
    cpp_value,
    get_config_fields,
    runtime_field_enum,
)
from gvrun.utils import write_if_changed


def _path_to_ident(path: str) -> str:
    """Convert a component path like /chip/soc/rom to a C identifier."""
    s = path.strip('/').replace('/', '_').replace('-', '_')
    return re.sub(r'[^a-zA-Z0-9_]', '_', s)


def _collect_full_tree(component, path=''):
    """
    Walk the Python component tree and collect everything needed for C++ generation.

    Returns a nested dict:
    {
        'name': str,
        'path': str,
        'children': {name: subtree, ...},
        'config_cls': type or None,
        'config_instance': object or None,
        'vp_component': str or None,
        'bindings': [(master_comp, master_port, slave_comp, slave_port), ...],
    }
    """
    config = getattr(component, '_component_config', None)
    config_cls = type(config) if config is not None and is_dataclass(config) else None

    # Get the vp_component module name
    vp_component = None
    props = getattr(component, 'properties', {})
    if isinstance(props, dict):
        vp_component = props.get('vp_component', None)

    # Get bindings
    bindings = []
    for binding in getattr(component, 'bindings', []):
        # binding is [master_comp, master_port, slave_comp, slave_port, master_props, slave_props]
        master_comp_obj = binding[0]
        master_port_name = binding[1]
        slave_comp_obj = binding[2]
        slave_port_name = binding[3]
        master_name = 'self' if master_comp_obj is component else master_comp_obj.name
        slave_name = 'self' if slave_comp_obj is component else slave_comp_obj.name
        bindings.append((master_name, master_port_name, slave_name, slave_port_name))

    node = {
        'name': getattr(component, 'name', '') or '',
        'path': path,
        'children': {},
        'config_cls': config_cls,
        'config_instance': config if config_cls else None,
        'vp_component': vp_component,
        'bindings': bindings,
    }

    for child_name, child in getattr(component, 'components', {}).items():
        child_path = f'{path}/{child_name}' if path else f'/{child_name}'
        node['children'][child_name] = _collect_full_tree(child, child_path)

    return node


def _add_class_includes(cls, includes: set) -> None:
    """Add the header for ``cls`` and any nested list-element configs to *includes*."""
    if cls is None:
        return
    includes.add(_header_include_path(cls))
    for fld in get_config_fields(cls):
        if fld['cpp_type'] == 'list':
            _add_class_includes(fld['list_elem_cls'], includes)


def _collect_includes(node) -> set:
    """Collect header includes from all config classes in the tree.

    Matches the layout written by _generate_platform_tree in
    gvsoc.runner_gvrun2: dotted module names ``pkg.sub.module`` map the
    header into ``pkg/snake.hpp``; a single-component module (e.g. a target
    file imported by name only) drops the header at the top of the build
    dir as ``snake.hpp``.
    """
    includes = set()
    if node['config_cls'] is not None:
        _add_class_includes(node['config_cls'], includes)
    for child in node['children'].values():
        includes |= _collect_includes(child)
    return includes


def _render_tree_cpp(component) -> str:
    """Render the per-target tree.cpp content from a Python component tree.

    Returns the file contents as a string. ``generate_tree_cpp`` writes it
    to disk; ``compute_signature`` hashes it for the runtime mismatch
    check (e.g. when ``--attribute`` reshapes the systree between build
    and run).
    """
    tree = _collect_full_tree(component)

    includes = _collect_includes(tree)

    lines = []
    lines.append('/*')
    lines.append(' * Auto-generated platform tree — do not edit manually.')
    lines.append(' */')
    lines.append('')
    lines.append('#include <cstddef>')
    lines.append('#include <vp/component_tree.hpp>')
    for inc in sorted(includes):
        lines.append(f'#include <{inc}>')
    lines.append('')

    # We collect all declarations bottom-up
    list_decls = []     # constexpr arrays for list-of-Config fields (emitted before the parent's struct init)
    config_decls = []   # config struct declarations (constexpr when frozen-only, static otherwise)
    runtime_decls = []  # runtime-field metadata tables
    binding_decls = []  # binding array declarations
    array_decls = []    # children array declarations
    node_decls = []     # node declarations

    def _format_aggregate(elem_cls, instance) -> str:
        """Render a nested Config instance as a brace-enclosed aggregate initializer.

        Mirrors the per-field policy of the top-level emitter: scalar fields
        produce literals, runtime fields are not allowed inside list elements
        (the engine only walks runtime tables on the root config), and nested
        lists recurse into ``_emit_list_array`` to emit a separate constexpr
        array referenced by pointer.
        """
        values = []
        for fld in get_config_fields(elem_cls):
            if fld['cpp_type'] == 'list':
                sub_arr = _emit_list_array(fld['list_elem_cls'],
                    getattr(instance, fld['name'], []) or [])
                values.append(str(len(getattr(instance, fld['name'], []) or [])))
                values.append(sub_arr)
                continue
            val = getattr(instance, fld['name'], fld['default'])
            if fld['cpp_type'] == 'int64_t' and isinstance(val, float):
                val = int(round(val))
            cv = cpp_value(val, fld['cpp_type'])
            if cv is None:
                # Unknown / unsupported value — fall back to a zero-style literal.
                if fld['cpp_type'] == 'const char *':
                    cv = 'nullptr'
                elif fld['cpp_type'] == 'bool':
                    cv = 'false'
                elif fld['cpp_type'] == 'double':
                    cv = '0.0'
                else:
                    cv = '0'
            values.append(cv)
        return '{' + ', '.join(values) + '}'

    _list_counter = [0]

    def _emit_list_array(elem_cls, items) -> str:
        """Emit a static constexpr array of ``elem_cls`` and return its identifier.

        Bottom-up: each item's aggregate string is rendered first, so any
        nested ``_list_N[]`` arrays they contain are appended to
        ``list_decls`` *before* this array's own declaration. Otherwise
        the inner declarations would land inside the outer array's brace
        block and the C++ would not parse.
        """
        if not items:
            return 'nullptr'
        # Render every aggregate first — this drains nested decls into
        # list_decls in dependency order.
        aggregates = [_format_aggregate(elem_cls, item) for item in items]
        idx = _list_counter[0]
        _list_counter[0] += 1
        arr_var = f'_list_{idx}'
        elem_name = elem_cls.__name__
        list_decls.append(f'static constexpr {elem_name} {arr_var}[] = {{')
        for agg in aggregates:
            list_decls.append(f'    {agg},')
        list_decls.append('};')
        return arr_var

    def emit_node(node, path=''):
        """Process a node bottom-up. Returns an inline initializer expression."""
        ident = _path_to_ident(path) if path else 'root'

        # Process children first
        child_exprs = []
        for child_name, child_node in node['children'].items():
            child_path = f'{path}/{child_name}' if path else f'/{child_name}'
            expr = emit_node(child_node, child_path)
            child_exprs.append(expr)

        # Emit config instance if any
        config_ptr = 'nullptr'
        runtime_ptr = 'nullptr'
        num_runtime_fields = '0'
        if node['config_cls'] is not None and node['config_instance'] is not None:
            var_name = f'_cfg_{ident}'
            fld_list = get_config_fields(node['config_cls'])
            values = []
            runtime_fields = []
            has_runtime = any(fld['runtime'] for fld in fld_list)
            for fld in fld_list:
                if fld['cpp_type'] == 'list':
                    items = getattr(node['config_instance'], fld['name'], []) or []
                    arr_expr = _emit_list_array(fld['list_elem_cls'], items)
                    values.append(str(len(items)))
                    values.append(arr_expr)
                    continue
                if fld['runtime']:
                    # Runtime fields are overlaid from JSON at component
                    # construction; emit a zero/nullptr placeholder here so
                    # the aggregate initializer stays well-formed.
                    cv = cpp_value(fld['default'], fld['cpp_type'])
                    if cv is None:
                        if fld['cpp_type'] == 'const char *':
                            cv = 'nullptr'
                        elif fld['cpp_type'] == 'bool':
                            cv = 'false'
                        elif fld['cpp_type'] == 'double':
                            cv = '0.0'
                        else:
                            cv = '0'
                    values.append(cv)
                    enum_name = runtime_field_enum(fld['cpp_type'])
                    runtime_fields.append((fld['name'], enum_name))
                    continue
                val = getattr(node['config_instance'], fld['name'], fld['default'])
                if fld['cpp_type'] == 'int64_t' and isinstance(val, float):
                    val = int(round(val))
                cv = cpp_value(val, fld['cpp_type'])
                if cv is not None:
                    values.append(cv)
            args = ', '.join(values)
            # A config that carries any runtime field cannot be constexpr:
            # the engine writes through the struct at construction to apply
            # the JSON-provided runtime values. Pure-frozen configs stay
            # constexpr (fastest, read-only image).
            storage = 'static' if has_runtime else 'static constexpr'
            config_decls.append(
                f'{storage} {node["config_cls"].__name__} {var_name}{{{args}}};')
            config_ptr = f'&{var_name}'

            if runtime_fields:
                rt_var = f'_runtime_fields_{ident}'
                type_name = node['config_cls'].__name__
                runtime_decls.append(
                    f'static constexpr vp::RuntimeField {rt_var}[] = {{')
                for fname, enum_name in runtime_fields:
                    runtime_decls.append(
                        f'    {{"{fname}", '
                        f'(unsigned int)offsetof({type_name}, {fname}), '
                        f'{enum_name}}},')
                runtime_decls.append('};')
                runtime_ptr = rt_var
                num_runtime_fields = str(len(runtime_fields))

        # Emit bindings array if any
        bindings_ptr = 'nullptr'
        num_bindings = '0'
        if node['bindings']:
            arr_var = f'_bindings_{ident}'
            binding_decls.append(f'static constexpr vp::TreeBinding {arr_var}[] = {{')
            for mc, mp, sc, sp in node['bindings']:
                binding_decls.append(f'    {{"{mc}", "{mp}", "{sc}", "{sp}"}},')
            binding_decls.append('};')
            bindings_ptr = arr_var
            num_bindings = str(len(node['bindings']))

        # Emit children array if any
        children_ptr = 'nullptr'
        num_children = '0'
        if child_exprs:
            arr_var = f'_children_{ident}'
            array_decls.append(f'static constexpr vp::ComponentTreeNode {arr_var}[] = {{')
            for expr in child_exprs:
                array_decls.append(f'    {expr},')
            array_decls.append('};')
            children_ptr = arr_var
            num_children = str(len(child_exprs))

        # vp_component
        vp_comp = f'"{node["vp_component"]}"' if node['vp_component'] else 'nullptr'

        name_str = f'"{node["name"]}"' if node['name'] else '""'

        expr = (f'{{{name_str}, {config_ptr}, {children_ptr}, {num_children}, '
                f'{vp_comp}, {bindings_ptr}, {num_bindings}, '
                f'{runtime_ptr}, {num_runtime_fields}}}')

        # Root node gets its own declaration
        if path == '':
            node_decls.append(
                f'static constexpr vp::ComponentTreeNode _node_root = {expr};')

        return expr

    emit_node(tree)

    # Write everything in order: list-of-Config arrays (must precede the
    # config_decls that reference them by name), configs, runtime metadata,
    # bindings, children arrays, nodes.
    for decl in list_decls:
        lines.append(decl)
    if list_decls:
        lines.append('')
    for decl in config_decls:
        lines.append(decl)
    if config_decls:
        lines.append('')
    for decl in runtime_decls:
        lines.append(decl)
    if runtime_decls:
        lines.append('')
    for decl in binding_decls:
        lines.append(decl)
    if binding_decls:
        lines.append('')
    for decl in array_decls:
        lines.append(decl)
    if array_decls:
        lines.append('')
    for decl in node_decls:
        lines.append(decl)

    lines.append('')
    lines.append('extern "C" const vp::ComponentTreeNode *vp_get_platform_tree()')
    lines.append('{')
    lines.append('    return &_node_root;')
    lines.append('}')
    lines.append('')

    return '\n'.join(lines)


def compute_signature(component) -> str:
    """SHA256 hex digest of the tree.cpp that would be written for ``component``.

    Used by the launcher at run time to decide whether the installed
    ``libplatform_tree_<target>.so`` (built against the default systree)
    still matches the live systree (which may have been reshaped by
    ``--attribute`` etc.). When the signature mismatches, the launcher
    skips ``platform_tree`` so the engine falls back to the JSON path
    instead of dlopen'ing a stale .so.
    """
    return hashlib.sha256(_render_tree_cpp(component).encode()).hexdigest()


def generate_tree_cpp(component, output_path: str) -> None:
    """Generate a C++ file with the compiled component tree.

    Also writes a ``<output_path>.sig`` sidecar containing the SHA256 of
    the tree.cpp content. The CMake install step copies that sidecar
    next to the compiled ``.so`` so the runtime can detect a stale
    ``.so`` (e.g. when ``--attribute`` changes the systree shape).

    Parameters
    ----------
    component : Component
        The root Python component (with .components, .bindings, .properties, etc.)
    output_path : str
        Path to write the generated .cpp file.
    """
    content = _render_tree_cpp(component)
    signature = hashlib.sha256(content.encode()).hexdigest()
    written = write_if_changed(output_path, content)
    write_if_changed(output_path + '.sig', signature)
    if written:
        print(f'Generated {output_path}')
    else:
        print(f'Up to date {output_path}')
