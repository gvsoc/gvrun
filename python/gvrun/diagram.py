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

"""
Generates a Graphviz (.dot) diagram from the GVSoC component tree.

The diagram shows:
  - Components as nodes (grouped by parent into subgraphs)
  - Port bindings as directed edges between components
  - Repeated similar components (e.g., memory banks) collapsed into single summary nodes
  - Hierarchical port-forwarding edges resolved to actual endpoints
"""

import re
from collections import defaultdict


# Color palette by nesting depth
_DEPTH_STYLES = [
    {"fill": "#e3f2fd", "border": "#1565c0", "node": "#90caf9"},   # blue
    {"fill": "#c8e6c9", "border": "#43a047", "node": "#a5d6a7"},   # green
    {"fill": "#fff3e0", "border": "#e65100", "node": "#ffcc80"},    # orange
    {"fill": "#fce4ec", "border": "#e53935", "node": "#f8bbd0"},    # pink
    {"fill": "#e8eaf6", "border": "#5c6bc0", "node": "#c5cae9"},    # indigo
    {"fill": "#d1c4e9", "border": "#7b1fa2", "node": "#b39ddb"},    # purple
    {"fill": "#fff9c4", "border": "#f9a825", "node": "#fff176"},    # yellow
    {"fill": "#ffebee", "border": "#c62828", "node": "#ef9a9a"},    # red
]

# Edge colors by interface type
_EDGE_STYLES = {
    'wide':    {'color': '#1565c0', 'penwidth': '2.5', 'label_prefix': 'Wide AXI'},
    'narrow':  {'color': '#43a047', 'penwidth': '1.5', 'label_prefix': 'Narrow AXI'},
    'tcdm':    {'color': '#e65100', 'penwidth': '2.0', 'label_prefix': 'TCDM'},
    'dma':     {'color': '#7b1fa2', 'penwidth': '2.0', 'label_prefix': 'DMA'},
    'fetch':   {'color': '#0288d1', 'penwidth': '1.0', 'style': 'dashed'},
    'control': {'color': '#999999', 'penwidth': '1.0', 'style': 'dashed'},
    'default': {'color': '#555555', 'penwidth': '1.0'},
}

# Infrastructure ports to skip
_INFRA_PORTS = {'clock', 'reset', 'power_supply', 'voltage'}


def _sanitize_id(path):
    return re.sub(r'[^a-zA-Z0-9_]', '_', path)


def _get_comp_path(comp):
    if hasattr(comp, 'get_path'):
        path = comp.get_path()
        if path is not None:
            return path
    parts = []
    c = comp
    while c is not None:
        if hasattr(c, 'name') and c.name is not None:
            parts.append(c.name)
        c = getattr(c, 'parent', None)
    parts.reverse()
    return '/'.join(parts) if parts else 'root'


def _format_size(size):
    if not isinstance(size, (int, float)):
        return str(size)
    if size >= 1024 * 1024 * 1024:
        return f'{size / (1024**3):.0f} GB'
    if size >= 1024 * 1024:
        return f'{size / (1024**2):.0f} MB'
    if size >= 1024:
        return f'{size // 1024} KB'
    return f'{size} B'


def _classify_edge(master_port, slave_port):
    """Determine the type of an edge based on port names."""
    ports = f'{master_port}_{slave_port}'.lower()

    if 'wide' in ports or ('axi' in ports and ('64' in ports or 'wide' in ports)):
        return 'wide'
    if 'fetch' in ports or 'icache' in ports or 'refill' in ports:
        return 'fetch'
    if 'tcdm' in ports or 'vlsu' in ports:
        return 'tcdm'
    if 'dma' in ports:
        return 'dma'
    if any(kw in ports for kw in ['irq', 'fetchen', 'flush', 'enable', 'grant',
                                   'offload', 'external', 'meip', 'start']):
        return 'control'
    if 'narrow' in ports:
        return 'narrow'
    if 'input' in ports or 'out' in ports or 'hbm' in ports:
        return 'narrow'  # default data path
    return 'default'


class DiagramBuilder:
    """Builds a graphviz diagram from the GVSoC component tree."""

    def __init__(self, top_component, target_name=None):
        self.top = top_component
        self.target_name = target_name or 'GVSoC Target'
        self.lines = []
        self.node_map = {}       # comp_path -> node_id
        self.leaf_nodes = set()  # set of node_ids that are actual graphviz nodes
        self.container_comps = set()  # paths of components that are subgraphs

        # For resolving hierarchical port forwarding
        # port_forwarding: (comp_path, port_name) -> (resolved_comp_path, resolved_port_name)
        self.port_forwarding = {}

    def build(self):
        self._emit(f'digraph "{self.target_name}" {{')
        self._emit('    rankdir=TB;')
        self._emit('    newrank=true;')
        self._emit('    fontname="Helvetica";')
        self._emit('    node [fontname="Helvetica", fontsize=9, shape=record, '
                   'style="filled,rounded"];')
        self._emit('    edge [fontname="Helvetica", fontsize=7];')
        self._emit('    compound=true;')
        self._emit('    splines=ortho;')
        self._emit('    nodesep=0.5;')
        self._emit('    ranksep=0.7;')
        self._emit('')
        self._emit(f'    label="{self.target_name} — Architecture Diagram\\n'
                   f'(auto-generated from GVSoC Python generators)";')
        self._emit('    labelloc=t;')
        self._emit('    fontsize=13;')
        self._emit('')

        # First pass: emit component hierarchy and register nodes
        self._emit_component(self.top, depth=0, is_top=True)
        self._emit('')

        # Second pass: resolve port forwarding and emit edges
        self._build_port_forwarding()
        self._emit('    // ===================== CONNECTIONS =====================')
        self._emit_bindings()

        # Legend
        self._emit('')
        self._emit_legend()

        self._emit('}')
        return '\n'.join(self.lines)

    def _emit(self, line):
        self.lines.append(line)

    def _emit_component(self, comp, depth, is_top=False):
        children = getattr(comp, 'components', {})
        path = _get_comp_path(comp)
        node_id = _sanitize_id(path)
        indent = '    ' * (depth + 1)
        style = _DEPTH_STYLES[depth % len(_DEPTH_STYLES)]

        self.node_map[path] = node_id

        if not children:
            # Leaf node
            self._emit_leaf(comp, path, node_id, depth, indent)
            return

        # Container
        self.container_comps.add(path)
        groups = _detect_groups(comp)

        if is_top:
            for group_name, members in groups.items():
                if len(members) >= 3:
                    self._emit_group(comp, group_name, members, depth, indent)
                else:
                    for name, child in members:
                        self._emit_component(child, depth)
            return

        cluster_name = f'cluster_{node_id}'
        name = getattr(comp, 'name', None) or type(comp).__name__
        self._emit(f'{indent}subgraph {cluster_name} {{')
        self._emit(f'{indent}    label="{name}";')
        self._emit(f'{indent}    style="filled,rounded"; '
                   f'fillcolor="{style["fill"]}"; color="{style["border"]}";')
        self._emit(f'{indent}    fontsize=10;')
        self._emit('')

        for group_name, members in groups.items():
            if len(members) >= 3:
                self._emit_group(comp, group_name, members, depth + 1,
                                 indent + '    ')
            else:
                for name, child in members:
                    self._emit_component(child, depth + 1)

        self._emit(f'{indent}}}')
        self._emit('')

    def _emit_leaf(self, comp, path, node_id, depth, indent):
        name = getattr(comp, 'name', None) or '?'
        info = _get_component_info(comp)
        style = _DEPTH_STYLES[depth % len(_DEPTH_STYLES)]

        label_parts = [name, f'({info["class"]})']
        extras = []
        if 'size' in info:
            extras.append(info['size'])
        if 'bandwidth' in info:
            extras.append(f'BW={info["bandwidth"]}')
        if extras:
            label_parts.append(', '.join(extras))

        label = '\\n'.join(label_parts)
        self._emit(f'{indent}{node_id} [label="{label}", fillcolor="{style["node"]}"];')
        self.leaf_nodes.add(node_id)

    def _emit_group(self, parent_comp, group_name, members, depth, indent):
        """Emit a group of similar components.

        - If the members are leaf components (no children), collapse all into a single summary node.
        - If the members are complex (have sub-components), show the first one expanded in detail
          and emit a summary node for the remaining N-1 instances.
        """
        _, first_child = members[0]
        first_has_children = len(getattr(first_child, 'components', {})) > 0

        if first_has_children:
            # Complex group: expand the first one, collapse the rest
            first_name, first_child = members[0]
            self._emit_component(first_child, depth)

            if len(members) > 1:
                # Summary node for the rest
                remaining = members[1:]
                self._emit_group_summary(parent_comp, group_name, first_name,
                                         remaining, depth, indent)
        else:
            # Simple leaf group: collapse all into one summary node
            self._emit_group_node(parent_comp, group_name, members, depth, indent)

    def _emit_group_summary(self, parent_comp, group_name, representative_name,
                            remaining_members, depth, indent):
        """Emit a summary node for remaining instances of a complex group."""
        style = _DEPTH_STYLES[depth % len(_DEPTH_STYLES)]
        count = len(remaining_members)

        _, first = remaining_members[0]
        info = _get_component_info(first)

        label = (f'{group_name} x{count} more\\n'
                 f'({info["class"]})\\n'
                 f'(same as {representative_name})')

        parent_path = _get_comp_path(parent_comp)
        group_path = f'{parent_path}/{group_name}_group'
        group_id = _sanitize_id(group_path)

        self._emit(f'{indent}{group_id} [label="{label}", fillcolor="{style["node"]}", '
                   f'shape=box3d, style="filled,rounded,dashed"];')

        self.node_map[group_path] = group_id
        self.leaf_nodes.add(group_id)

        # Map all remaining member paths to this summary node
        for name, child in remaining_members:
            child_path = _get_comp_path(child)
            self.node_map[child_path] = group_id
            # Also map all descendants of collapsed members
            self._map_descendants(child, group_id)

    def _map_descendants(self, comp, target_id):
        """Recursively map all descendants of a component to a target node ID."""
        for child_name, child in getattr(comp, 'components', {}).items():
            child_path = _get_comp_path(child)
            self.node_map[child_path] = target_id
            self._map_descendants(child, target_id)

    def _emit_group_node(self, parent_comp, group_name, members, depth, indent):
        style = _DEPTH_STYLES[depth % len(_DEPTH_STYLES)]
        _, first_child = members[0]
        info = _get_component_info(first_child)
        count = len(members)

        total_size = 0
        all_have_size = True
        for _, child in members:
            props = getattr(child, 'properties', {})
            if isinstance(props, dict) and 'size' in props:
                s = props['size']
                if isinstance(s, (int, float)):
                    total_size += s
                else:
                    all_have_size = False
            else:
                all_have_size = False

        label_parts = [f'{group_name} x{count}', f'({info["class"]})']
        if all_have_size and total_size > 0:
            per_unit = _format_size(total_size // count)
            total = _format_size(total_size)
            label_parts.append(f'{per_unit} each, {total} total')
        elif 'bandwidth' in info:
            label_parts.append(f'BW={info["bandwidth"]}')

        label = '\\n'.join(label_parts)

        parent_path = _get_comp_path(parent_comp)
        group_path = f'{parent_path}/{group_name}_group'
        group_id = _sanitize_id(group_path)

        self._emit(f'{indent}{group_id} [label="{label}", fillcolor="{style["node"]}", '
                   f'shape=box3d];')

        self.node_map[group_path] = group_id
        self.leaf_nodes.add(group_id)
        for name, child in members:
            child_path = _get_comp_path(child)
            self.node_map[child_path] = group_id

    def _build_port_forwarding(self):
        """Build a map that resolves hierarchical port forwarding.

        When a container component binds `self->port_a` to `child->port_b`,
        it means port_a on the container is actually port_b on the child.
        We follow these chains to resolve to leaf endpoints.
        """
        all_bindings = []
        self._collect_bindings(self.top, all_bindings)

        # Build forwarding table: (comp_path, port) -> (comp_path, port)
        fwd = {}
        for binding in all_bindings:
            master_comp, master_port, slave_comp, slave_port = binding[0], binding[1], binding[2], binding[3]
            master_path = _get_comp_path(master_comp)
            slave_path = _get_comp_path(slave_comp)

            # Check if this is a parent binding with self
            parent = getattr(master_comp, 'parent', None) if hasattr(master_comp, 'parent') else None

            # Self → child: the container's port is forwarded to the child's port
            if master_path in self.container_comps and slave_path != master_path:
                # master (container) port → slave (child) port
                fwd[(master_path, master_port)] = (slave_path, slave_port)

            if slave_path in self.container_comps and master_path != slave_path:
                # child → container port: the container's port is forwarded from the child
                fwd[(slave_path, slave_port)] = (master_path, master_port)

        self.port_forwarding = fwd

    def _resolve_endpoint(self, comp_path, port, depth=0):
        """Resolve a (comp_path, port) through forwarding chains to a leaf."""
        if depth > 20:
            return comp_path, port

        node_id = self.node_map.get(comp_path)
        if node_id is not None and node_id in self.leaf_nodes:
            return comp_path, port

        # Try forwarding
        resolved = self.port_forwarding.get((comp_path, port))
        if resolved is not None:
            return self._resolve_endpoint(resolved[0], resolved[1], depth + 1)

        return comp_path, port

    def _emit_bindings(self):
        all_bindings = []
        self._collect_bindings(self.top, all_bindings)

        seen = set()

        for binding in all_bindings:
            master_comp, master_port = binding[0], binding[1]
            slave_comp, slave_port = binding[2], binding[3]

            if master_port in _INFRA_PORTS or slave_port in _INFRA_PORTS:
                continue

            master_path = _get_comp_path(master_comp)
            slave_path = _get_comp_path(slave_comp)

            if master_path == slave_path:
                continue

            # Resolve through forwarding
            master_path, master_port = self._resolve_endpoint(master_path, master_port)
            slave_path, slave_port = self._resolve_endpoint(slave_path, slave_port)

            master_id = self.node_map.get(master_path, _sanitize_id(master_path))
            slave_id = self.node_map.get(slave_path, _sanitize_id(slave_path))

            # Skip if either endpoint doesn't have a real node
            if master_id not in self.leaf_nodes or slave_id not in self.leaf_nodes:
                continue

            if master_id == slave_id:
                continue

            edge_key = (master_id, slave_id, master_port, slave_port)
            dedup_key = (master_id, slave_id)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            # Classify and style the edge
            edge_type = _classify_edge(master_port, slave_port)
            estyl = _EDGE_STYLES.get(edge_type, _EDGE_STYLES['default'])

            attrs = [
                f'color="{estyl["color"]}"',
                f'penwidth={estyl["penwidth"]}',
            ]

            if 'style' in estyl:
                attrs.append(f'style={estyl["style"]}')

            # Tooltip with port info
            attrs.append(f'edgetooltip="{master_port} → {slave_port}"')

            # Label for mapped regions
            label_parts = []
            for props in [binding[4] if len(binding) > 4 else None,
                          binding[5] if len(binding) > 5 else None]:
                if props and isinstance(props, dict):
                    base = props.get('base')
                    size = props.get('size')
                    if base is not None:
                        label_parts.append(f'0x{base:x}')
                    if size is not None:
                        label_parts.append(_format_size(size))
            if label_parts:
                attrs.append(f'label="{", ".join(label_parts)}"')

            attr_str = f' [{", ".join(attrs)}]'
            self._emit(f'    {master_id} -> {slave_id}{attr_str};')

    def _emit_legend(self):
        """Emit a legend subgraph."""
        self._emit('    subgraph cluster_legend {')
        self._emit('        label="Legend";')
        self._emit('        style="filled,rounded"; fillcolor="#f5f5f5"; color="#cccccc";')
        self._emit('        fontsize=10;')
        self._emit('        node [shape=plaintext, fillcolor="#f5f5f5"];')
        self._emit('')
        self._emit('        legend [label=<')
        self._emit('            <TABLE BORDER="0" CELLBORDER="0" CELLSPACING="4">')
        for name, estyl in [
            ('Wide AXI (512b)', _EDGE_STYLES['wide']),
            ('Narrow AXI (64b)', _EDGE_STYLES['narrow']),
            ('TCDM / VLSU', _EDGE_STYLES['tcdm']),
            ('DMA', _EDGE_STYLES['dma']),
            ('Instruction fetch', _EDGE_STYLES['fetch']),
            ('Control / IRQ', _EDGE_STYLES['control']),
        ]:
            self._emit(f'            <TR><TD><FONT COLOR="{estyl["color"]}">━━━</FONT></TD>'
                       f'<TD ALIGN="LEFT"><FONT POINT-SIZE="8">{name}</FONT></TD></TR>')
        self._emit('            <TR><TD></TD><TD ALIGN="LEFT">'
                   '<FONT POINT-SIZE="8">Arrow = master → slave</FONT></TD></TR>')
        self._emit('            </TABLE>')
        self._emit('        >];')
        self._emit('    }')

    def _collect_bindings(self, comp, result):
        for binding in getattr(comp, 'bindings', []):
            result.append(binding)
        for child in getattr(comp, 'components', {}).values():
            self._collect_bindings(child, result)


def _get_component_info(comp):
    class_name = type(comp).__name__
    props = getattr(comp, 'properties', {})
    info = {'class': class_name}

    if isinstance(props, dict):
        size = props.get('size')
        if size is not None and isinstance(size, (int, float)):
            info['size'] = _format_size(size)
        bw = props.get('bandwidth')
        if bw is not None:
            info['bandwidth'] = f'{bw}B'

    return info


def _detect_groups(comp):
    children = getattr(comp, 'components', {})
    if not children:
        return {}

    by_class = defaultdict(list)
    for name, child in children.items():
        child_class = type(child).__name__
        base = re.sub(r'_?\d+$', '', name)
        key = (base, child_class)
        by_class[key].append((name, child))

    groups = {}
    for (base, cls), members in by_class.items():
        if len(members) >= 3:
            groups[base] = members
        else:
            for name, child in members:
                groups[name] = [(name, child)]

    return groups


def generate_diagram(top_component, output_path, target_name=None):
    """Generate a Graphviz .dot file from the GVSoC component tree.

    Parameters
    ----------
    top_component : Component
        The top-level component of the system.
    output_path : str
        Path where the .dot file should be written.
    target_name : str, optional
        Name of the target for the diagram title.
    """
    builder = DiagramBuilder(top_component, target_name)
    dot_content = builder.build()

    with open(output_path, 'w') as f:
        f.write(dot_content)

    print(f'Diagram written to {output_path}')
