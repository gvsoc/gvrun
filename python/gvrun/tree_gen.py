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
import os
import re
from dataclasses import fields, is_dataclass


# Reuse field helpers from config_gen
from gvrun.config_gen import get_config_fields, cpp_value, _SKIP_FIELDS


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


def _collect_includes(node) -> set:
    """Collect header includes from all config classes in the tree."""
    includes = set()
    if node['config_cls'] is not None:
        cls = node['config_cls']
        mod = cls.__module__
        parts = mod.split('.')
        if len(parts) >= 2:
            subdir = parts[0]
            snake = re.sub(r'(?<!^)(?=[A-Z])', '_', cls.__name__).lower()
            includes.add(f'{subdir}/{snake}.hpp')
    for child in node['children'].values():
        includes |= _collect_includes(child)
    return includes


def generate_tree_cpp(component, output_path: str) -> None:
    """
    Generate a C++ file with the compiled component tree.

    Parameters
    ----------
    component : Component
        The root Python component (with .components, .bindings, .properties, etc.)
    output_path : str
        Path to write the generated .cpp file.
    """
    tree = _collect_full_tree(component)

    includes = _collect_includes(tree)

    lines = []
    lines.append('/*')
    lines.append(' * Auto-generated platform tree — do not edit manually.')
    lines.append(' */')
    lines.append('')
    lines.append('#include <vp/component_tree.hpp>')
    for inc in sorted(includes):
        lines.append(f'#include <{inc}>')
    lines.append('')

    # We collect all declarations bottom-up
    config_decls = []   # constexpr config declarations
    binding_decls = []  # binding array declarations
    array_decls = []    # children array declarations
    node_decls = []     # node declarations

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
        if node['config_cls'] is not None and node['config_instance'] is not None:
            var_name = f'_cfg_{ident}'
            fld_list = get_config_fields(node['config_cls'])
            values = []
            for fld in fld_list:
                val = getattr(node['config_instance'], fld['name'], fld['default'])
                if fld['cpp_type'] == 'int64_t' and isinstance(val, float):
                    val = int(round(val))
                cv = cpp_value(val, fld['cpp_type'])
                if cv is not None:
                    values.append(cv)
            args = ', '.join(values)
            config_decls.append(
                f'static constexpr {node["config_cls"].__name__} {var_name}{{{args}}};')
            config_ptr = f'&{var_name}'

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
                f'{vp_comp}, {bindings_ptr}, {num_bindings}}}')

        # Root node gets its own declaration
        if path == '':
            node_decls.append(
                f'static constexpr vp::ComponentTreeNode _node_root = {expr};')

        return expr

    emit_node(tree)

    # Write everything in order: configs, bindings, children arrays, nodes
    for decl in config_decls:
        lines.append(decl)
    if config_decls:
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

    content = '\n'.join(lines)
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    with open(output_path, 'w') as fp:
        fp.write(content)
    print(f'Generated {output_path}')
