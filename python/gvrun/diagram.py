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
Generates a Graphviz (.dot) diagram from the GVSoC component tree.

The diagram shows:
  - Components as nodes (grouped by parent into subgraphs)
  - Port bindings as directed edges between components
  - Repeated similar components (e.g., memory banks) collapsed into single summary nodes
  - Hierarchical port-forwarding edges resolved to actual endpoints
  - Auto-generated legend based on the edge types actually present in the target
"""

import re
from collections import defaultdict, OrderedDict


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

# A pool of distinguishable colors for auto-assigned edge categories
_EDGE_COLOR_POOL = [
    '#1565c0',  # blue
    '#43a047',  # green
    '#e65100',  # orange
    '#7b1fa2',  # purple
    '#0288d1',  # light blue
    '#c62828',  # red
    '#00838f',  # teal
    '#4e342e',  # brown
    '#ad1457',  # pink
    '#1b5e20',  # dark green
    '#e65100',  # deep orange
    '#283593',  # indigo
]

# Infrastructure ports to skip
_INFRA_PORTS = {'clock', 'reset', 'power_supply', 'voltage'}

# Control signal keywords (for any architecture)
_CONTROL_KEYWORDS = [
    'irq', 'interrupt', 'fetchen', 'flush', 'enable', 'grant', 'offload',
    'external', 'meip', 'start', 'entry', 'barrier', 'wake', 'halt',
    'debug', 'ebreak', 'reset', 'ack', 'err', 'busy', 'ready', 'valid',
]

# Instruction fetch keywords
_FETCH_KEYWORDS = ['fetch', 'icache', 'refill', 'instr']


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


def _get_bandwidth(comp):
    """Get the bandwidth property of a component, if any."""
    props = getattr(comp, 'properties', {})
    if isinstance(props, dict):
        bw = props.get('bandwidth')
        if bw is not None and isinstance(bw, (int, float)):
            return int(bw)
    return None


class EdgeClassifier:
    """Discovers and classifies edge types based on actual component properties.

    Instead of hardcoded categories, this builds categories dynamically:
    - Data paths are classified by bandwidth (from router/interconnect properties)
    - Instruction fetch paths detected by port name keywords
    - Control/IRQ paths detected by port name keywords
    - DMA paths detected by component class or port names
    - Everything else gets a generic 'data' category
    """

    def __init__(self):
        # comp_path -> component info dict
        self.comp_info = {}
        # Discovered categories: key -> {label, color, penwidth, style, order}
        self.categories = OrderedDict()
        self._color_idx = 0

    def register_component(self, comp):
        """Register a component's properties for later edge classification."""
        path = _get_comp_path(comp)
        cls_name = type(comp).__name__
        bw = _get_bandwidth(comp)
        self.comp_info[path] = {
            'class': cls_name,
            'bandwidth': bw,
        }

    def classify(self, master_comp, master_port, slave_comp, slave_port):
        """Classify an edge and return a category key.

        The category is auto-created if not yet seen.
        """
        ports_lower = f'{master_port}_{slave_port}'.lower()
        master_path = _get_comp_path(master_comp)
        slave_path = _get_comp_path(slave_comp)
        master_info = self.comp_info.get(master_path, {})
        slave_info = self.comp_info.get(slave_path, {})
        master_cls = master_info.get('class', '').lower()
        slave_cls = slave_info.get('class', '').lower()

        # 1. Control / IRQ signals
        if any(kw in ports_lower for kw in _CONTROL_KEYWORDS):
            return self._ensure_category('control', 'Control / IRQ',
                                         penwidth='1.0', style='dashed',
                                         priority=90)

        # 2. Instruction fetch
        if any(kw in ports_lower for kw in _FETCH_KEYWORDS):
            return self._ensure_category('fetch', 'Instruction fetch',
                                         penwidth='1.5', style='dashed',
                                         priority=80)

        # 3. DMA paths
        if 'dma' in ports_lower or 'dma' in master_cls or 'dma' in slave_cls:
            return self._ensure_category('dma', 'DMA',
                                         penwidth='2.0', priority=30)

        # 4. Data paths — classify by bandwidth
        # Look at the bandwidth of the master or slave if they're routers/interconnects
        bw = None
        router_classes = ['router', 'interleaver', 'crossbar', 'xbar', 'noc', 'axi']
        for info in [master_info, slave_info]:
            cls = info.get('class', '').lower()
            if any(rc in cls for rc in router_classes) and info.get('bandwidth'):
                bw = info['bandwidth']
                break

        if bw is not None:
            cat_key = f'data_{bw}B'
            label = f'Data path ({bw}B = {bw*8}b)'
            pw = '1.5' if bw <= 8 else ('2.0' if bw <= 32 else '2.5')
            return self._ensure_category(cat_key, label, penwidth=pw, priority=bw)

        # 5. Memory / interleaver paths (TCDM-like)
        mem_keywords = ['tcdm', 'vlsu', 'spm', 'scratchpad', 'l1']
        if any(kw in ports_lower for kw in mem_keywords) or \
           any(kw in master_cls for kw in mem_keywords) or \
           any(kw in slave_cls for kw in mem_keywords):
            return self._ensure_category('local_mem', 'Local memory',
                                         penwidth='2.0', priority=40)

        # 6. Default data path
        return self._ensure_category('data', 'Data',
                                     penwidth='1.0', priority=50)

    def _ensure_category(self, key, label, penwidth='1.0', style=None, priority=50):
        """Ensure a category exists; create it with an auto-assigned color if new."""
        if key not in self.categories:
            color = self._next_color()
            cat = {
                'label': label,
                'color': color,
                'penwidth': penwidth,
                'priority': priority,
            }
            if style:
                cat['style'] = style
            self.categories[key] = cat
        return key

    def _next_color(self):
        """Get the next color from the pool."""
        color = _EDGE_COLOR_POOL[self._color_idx % len(_EDGE_COLOR_POOL)]
        self._color_idx += 1
        return color

    def get_style(self, category_key):
        """Get the visual style for a category."""
        return self.categories.get(category_key, {
            'color': '#555555', 'penwidth': '1.0', 'label': 'Unknown'
        })

    def get_legend_entries(self):
        """Return legend entries sorted by priority, only for categories that were used."""
        entries = sorted(self.categories.items(),
                         key=lambda x: x[1].get('priority', 50))
        return [(cat['label'], cat) for _, cat in entries]


class DiagramBuilder:
    """Builds a graphviz diagram from the GVSoC component tree."""

    def __init__(self, top_component, target_name=None, group_similar=True):
        self.top = top_component
        self.target_name = target_name or 'GVSoC Target'
        self.group_similar = group_similar
        self.lines = []
        self.node_map = {}       # comp_path -> node_id
        self.leaf_nodes = set()  # set of node_ids that are actual graphviz nodes
        self.container_comps = set()  # paths of components that are subgraphs
        self.port_forwarding = {}
        self.edge_classifier = EdgeClassifier()
        # Track which categories are actually emitted
        self.used_categories = set()

    def build(self):
        # Register all components for classification
        self._register_all_components(self.top)

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

        # Legend (auto-generated from used categories)
        self._emit('')
        self._emit_legend()

        self._emit('}')
        return '\n'.join(self.lines)

    def _register_all_components(self, comp):
        """Register all components in the tree for edge classification."""
        self.edge_classifier.register_component(comp)
        for child in getattr(comp, 'components', {}).values():
            self._register_all_components(child)

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
            self._emit_leaf(comp, path, node_id, depth, indent)
            return

        self.container_comps.add(path)

        if is_top:
            if self.group_similar:
                groups = _detect_groups(comp)
                for group_name, members in groups.items():
                    if len(members) >= 3:
                        self._emit_group(comp, group_name, members, depth, indent)
                    else:
                        for name, child in members:
                            self._emit_component(child, depth)
            else:
                for child_name, child in children.items():
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

        if self.group_similar:
            groups = _detect_groups(comp)
            for group_name, members in groups.items():
                if len(members) >= 3:
                    self._emit_group(comp, group_name, members, depth + 1,
                                     indent + '    ')
                else:
                    for name, child in members:
                        self._emit_component(child, depth + 1)
        else:
            for child_name, child in children.items():
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
        _, first_child = members[0]
        first_has_children = len(getattr(first_child, 'components', {})) > 0

        if first_has_children:
            first_name, first_child = members[0]
            self._emit_component(first_child, depth)
            if len(members) > 1:
                remaining = members[1:]
                self._emit_group_summary(parent_comp, group_name, first_name,
                                         remaining, depth, indent)
        else:
            self._emit_group_node(parent_comp, group_name, members, depth, indent)

    def _emit_group_summary(self, parent_comp, group_name, representative_name,
                            remaining_members, depth, indent):
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

        for name, child in remaining_members:
            child_path = _get_comp_path(child)
            self.node_map[child_path] = group_id
            self._map_descendants(child, group_id)

    def _map_descendants(self, comp, target_id):
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
        all_bindings = []
        self._collect_bindings(self.top, all_bindings)

        fwd = {}
        for binding in all_bindings:
            master_comp, master_port, slave_comp, slave_port = \
                binding[0], binding[1], binding[2], binding[3]
            master_path = _get_comp_path(master_comp)
            slave_path = _get_comp_path(slave_comp)

            if master_path in self.container_comps and slave_path != master_path:
                fwd[(master_path, master_port)] = (slave_path, slave_port)

            if slave_path in self.container_comps and master_path != slave_path:
                fwd[(slave_path, slave_port)] = (master_path, master_port)

        self.port_forwarding = fwd

    def _resolve_endpoint(self, comp_path, port, depth=0):
        if depth > 20:
            return comp_path, port

        node_id = self.node_map.get(comp_path)
        if node_id is not None and node_id in self.leaf_nodes:
            return comp_path, port

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

            # Classify using original components (before resolution)
            cat_key = self.edge_classifier.classify(
                master_comp, master_port, slave_comp, slave_port)

            # Resolve through forwarding
            master_path, master_port = self._resolve_endpoint(master_path, master_port)
            slave_path, slave_port = self._resolve_endpoint(slave_path, slave_port)

            master_id = self.node_map.get(master_path, _sanitize_id(master_path))
            slave_id = self.node_map.get(slave_path, _sanitize_id(slave_path))

            if master_id not in self.leaf_nodes or slave_id not in self.leaf_nodes:
                continue

            if master_id == slave_id:
                continue

            dedup_key = (master_id, slave_id)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            # Get style from classifier
            estyl = self.edge_classifier.get_style(cat_key)
            self.used_categories.add(cat_key)

            attrs = [
                f'color="{estyl["color"]}"',
                f'penwidth={estyl["penwidth"]}',
            ]

            if 'style' in estyl:
                attrs.append(f'style={estyl["style"]}')

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
        """Emit a legend subgraph with only the edge types that actually appear."""
        legend_entries = self.edge_classifier.get_legend_entries()
        # Filter to only used categories
        legend_entries = [(label, cat) for label, cat in legend_entries
                          if any(k in self.used_categories
                                 for k, v in self.edge_classifier.categories.items()
                                 if v['label'] == label)]

        if not legend_entries:
            return

        self._emit('    subgraph cluster_legend {')
        self._emit('        label="Legend";')
        self._emit('        style="filled,rounded"; fillcolor="#f5f5f5"; color="#cccccc";')
        self._emit('        fontsize=10;')
        self._emit('        node [shape=plaintext, fillcolor="#f5f5f5"];')
        self._emit('')
        self._emit('        legend [label=<')
        self._emit('            <TABLE BORDER="0" CELLBORDER="0" CELLSPACING="4">')

        for label, cat in legend_entries:
            line_style = '━━━' if 'style' not in cat else '╌╌╌'
            self._emit(f'            <TR><TD><FONT COLOR="{cat["color"]}">{line_style}</FONT></TD>'
                       f'<TD ALIGN="LEFT"><FONT POINT-SIZE="8">{label}</FONT></TD></TR>')

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


def _compute_base_name(name):
    """Compute a base name for grouping by removing numeric indices.

    Examples:
        pe0       → pe
        pe0_ico   → pe_ico
        bank_0    → bank
        bank_31   → bank
        cluster_0 → cluster
        l0_bank0  → l0_bank
    """
    return re.sub(r'_?\d+', '', name)


def _detect_groups(comp):
    children = getattr(comp, 'components', {})
    if not children:
        return {}

    by_class = defaultdict(list)
    for name, child in children.items():
        child_class = type(child).__name__
        base = _compute_base_name(name)
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


def generate_diagram(top_component, output_path, target_name=None, group_similar=True):
    """Generate a Graphviz .dot file from the GVSoC component tree.

    Parameters
    ----------
    top_component : Component
        The top-level component of the system.
    output_path : str
        Path where the .dot file should be written.
    target_name : str, optional
        Name of the target for the diagram title.
    group_similar : bool, optional
        If True (default), group repeated similar components. If False, show all instances.
    """
    builder = DiagramBuilder(top_component, target_name, group_similar=group_similar)
    dot_content = builder.build()

    with open(output_path, 'w') as f:
        f.write(dot_content)

    print(f'Diagram written to {output_path}')
