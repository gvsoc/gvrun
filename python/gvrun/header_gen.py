#
# Copyright (C) 2020 ETH Zurich and University of Bologna
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
Generate C ``#define`` headers from a ``config_tree.Config`` hierarchy.

This module provides two entry points:

- :func:`generate_header` — emit a single flat header for the entire tree.
- :func:`generate_headers` — emit one standalone header per Config level
  (leaf configs inlined into their parent's header).

Both operate on ``config_tree.Config`` instances.  Scalar fields with
``read=True`` are emitted as ``#define`` directives.  Child configs
(from ``config.children``) provide the tree structure for recursion.
"""

from __future__ import annotations

import enum
import os
from dataclasses import fields
from typing import Any

from config_tree import Config


# Fields inherited from the Config base class — never emitted as defines.
_BASE_FIELD_NAMES = frozenset({
    "name", "label", "path", "parent", "children", "links", "defines",
})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_readable(config: Config, field_name: str) -> bool:
    """Return True if the field should be emitted (read flag is set)."""
    flags = getattr(config, '_field_flags', {})
    return flags.get(field_name, {}).get('read', False)


def _format_leaf(value: Any, fmt: str | None) -> str | None:
    """Format a leaf value as a C literal string, or None if not representable."""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return f"0x{value:08x}" if fmt == "hex" else str(value)
    if isinstance(value, float):
        return str(value)
    if isinstance(value, str):
        return f'"{value}"'
    if isinstance(value, enum.Enum):
        v = value.value
        return str(v) if isinstance(v, int) else f'"{v}"'
    return None


def _collect_scalar_defines(
    config: Config,
    prefix: str,
) -> list[tuple[str, str, str]]:
    """Collect (define_name, c_value, description) for readable scalar fields."""
    result: list[tuple[str, str, str]] = []
    for f in fields(config):
        if f.name in _BASE_FIELD_NAMES or not _is_readable(config, f.name):
            continue
        value = getattr(config, f.name, None)
        if value is None or isinstance(value, Config):
            continue
        # Skip lists/tuples of Configs (children handle those)
        if isinstance(value, (list, tuple)) and value and isinstance(value[0], Config):
            continue
        define_name = f"{prefix}_{f.name.upper()}"
        desc = f.metadata.get("description", "") if f.metadata else ""
        fmt = f.metadata.get("format") if f.metadata else None
        c_value = _format_leaf(value, fmt)
        if c_value is not None:
            result.append((define_name, c_value, desc))
    return result


def _get_local_prefix(config: Config, fallback: str = "CONFIG") -> str:
    """Return the define prefix for a Config node."""
    if config.name:
        return f"CONFIG_{config.name.upper()}"
    return fallback


def _has_children(config: Config) -> bool:
    """Return True if *config* has child Config nodes (adopted or in fields/attrs)."""
    if config.children:
        return True
    # Check all instance attributes for Config instances not tracked in children.
    for attr_name, value in vars(config).items():
        if attr_name.startswith('_') or attr_name in _BASE_FIELD_NAMES:
            continue
        if value is None:
            continue
        if isinstance(value, Config):
            return True
        if isinstance(value, (list, tuple)) and value and isinstance(value[0], Config):
            return True
    return False


# ---------------------------------------------------------------------------
# Single flat header
# ---------------------------------------------------------------------------

def _collect_defines(
    config: Config,
    prefix: str = "CONFIG",
    section_path: list[str] | None = None,
    depth: int = 0,
) -> list[dict]:
    """Recursively collect C preprocessor define entries from a config tree.

    Walks scalar fields for defines and ``config.children`` for hierarchy.
    """
    if section_path is None:
        section_path = []

    # Scalar fields → leaf defines
    leaves: list[dict] = []
    for name, value, desc in _collect_scalar_defines(config, prefix):
        leaves.append({
            "kind": "define",
            "name": name,
            "value": value,
            "desc": desc,
        })

    # Children → sections
    sections: list[dict] = []
    for child in _iter_config_children(config):
        child_prefix = f"{prefix}_{child.name.upper()}"
        label = child.name.upper().replace("_", " ")
        children = _collect_defines(
            child, child_prefix, section_path + [label], depth + 1)
        if children:
            sections.append({
                "kind": "section",
                "label": " / ".join(section_path + [label]),
                "depth": depth + 1,
                "children": children,
            })

    return leaves + sections


def generate_header(
    config: Config,
    path: str,
    prefix: str = "CONFIG",
    guard: str | None = None,
) -> None:
    """Generate a single flat C header with ``#define`` directives.

    Args:
        config: Root config to walk.
        path:   Output file path.
        prefix: Prefix for all define names.
        guard:  Include-guard macro name (derived from *path* if None).
    """
    tree = _collect_defines(config, prefix)

    if guard is None:
        guard = "_" + os.path.basename(path).upper().replace(".", "_").replace("-", "_") + "_"

    all_defines: list[dict] = []
    def _gather(entries: list[dict]) -> None:
        for e in entries:
            if e["kind"] == "define":
                all_defines.append(e)
            elif e["kind"] == "section":
                _gather(e["children"])
    _gather(tree)

    max_name_len = max((len(d["name"]) for d in all_defines), default=0)

    lines: list[str] = []
    lines.append(f"#ifndef {guard}")
    lines.append(f"#define {guard}")
    lines.append("")
    lines.append("/* Auto-generated from Config tree — do not edit */")

    def _render(entries: list[dict], depth: int) -> None:
        for e in entries:
            if e["kind"] == "section":
                label = e["label"]
                d = e["depth"]
                lines.append("")
                if d <= 1:
                    banner_len = max(len(label) + 6, 40)
                    lines.append("/* " + "=" * banner_len + " */")
                    padding_total = banner_len - len(label)
                    left = padding_total // 2
                    right = padding_total - left
                    lines.append("/* " + " " * left + label + " " * right + " */")
                    lines.append("/* " + "=" * banner_len + " */")
                else:
                    lines.append("/* " + "-" * 4 + " " + label + " " + "-" * 4 + " */")
                _render(e["children"], depth + 1)
            elif e["kind"] == "define":
                padding = " " * (max_name_len - len(e["name"]) + 2)
                lines.append(f"#define {e['name']}{padding}{e['value']}")

    _render(tree, 0)

    lines.append("")
    lines.append(f"#endif /* {guard} */")
    lines.append("")

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w") as fh:
        fh.write("\n".join(lines))


# ---------------------------------------------------------------------------
# Per-level header hierarchy
# ---------------------------------------------------------------------------

def _iter_config_children(config: Config):
    """Yield child Config instances from ``config.children`` and instance attributes.

    ``config.children`` is the primary source (populated by ``adopt()``).
    As a fallback, all instance attributes are scanned for Config instances
    or lists/tuples of Config instances so that configs stored as plain
    attributes (e.g. ``self.mapping = RouterMapping(...)``) or in list fields
    (e.g. ``RouterConfig.mappings``) are discovered even when not explicitly
    adopted.  Already-seen configs (by identity) are skipped to avoid
    duplicates.
    """
    seen: set[int] = set()
    for child in config.children:
        seen.add(id(child))
        yield child

    # Scan instance attributes for Config instances not already in children.
    for attr_name, value in vars(config).items():
        if value is None or attr_name.startswith('_') or attr_name in _BASE_FIELD_NAMES:
            continue
        if isinstance(value, Config):
            if id(value) not in seen:
                seen.add(id(value))
                yield value
        elif isinstance(value, (list, tuple)) and value and isinstance(value[0], Config):
            for item in value:
                if id(item) not in seen:
                    seen.add(id(item))
                    yield item


def _generate_header_tree(
    config: Config,
    outdir: str,
    rel_dir: str,
    filename: str,
    fallback_prefix: str = "CONFIG",
) -> None:
    """Recursively generate one standalone header per Config level.

    Scalar fields → ``#define`` in this node's header.
    Leaf children (no grandchildren) → inlined into this header with a banner.
    Non-leaf children → recurse into their own header file.
    """
    prefix = _get_local_prefix(config, fallback_prefix)
    my_rel_path = os.path.join(rel_dir, filename) if rel_dir else filename

    leaf_defines = _collect_scalar_defines(config, prefix)

    # Walk children: inline leaves, recurse non-leaves
    inlined_sections: list[tuple[str, list[tuple[str, str, str]]]] = []
    for child in _iter_config_children(config):
        child_prefix = f"{prefix}_{child.name.upper()}"
        label = child.name.upper().replace("_", " ")

        if _has_children(child):
            # Non-leaf child → its own header file
            child_rel = os.path.join(rel_dir, child.name)
            _generate_header_tree(
                child, outdir, child_rel, "config.h", child_prefix)
        else:
            # Leaf child → inline into parent's header
            child_defs = _collect_scalar_defines(child, child_prefix)
            if child_defs:
                inlined_sections.append((label, child_defs))

    # Compute alignment across all defines in this file
    all_names: list[str] = [n for n, _, _ in leaf_defines]
    for _, defs in inlined_sections:
        all_names += [n for n, _, _ in defs]
    max_len = max((len(n) for n in all_names), default=0)

    # Build file content
    guard_name = "_" + my_rel_path.upper() \
        .replace("/", "_").replace(".", "_").replace("-", "_") + "_"

    lines: list[str] = []
    lines.append(f"#ifndef {guard_name}")
    lines.append(f"#define {guard_name}")
    lines.append("")
    lines.append("/* Auto-generated from Config tree — do not edit */")

    if leaf_defines:
        lines.append("")
        for name, value, desc in leaf_defines:
            if desc:
                lines.append(f"/* {desc} */")
            padding = " " * (max_len - len(name) + 2)
            lines.append(f"#define {name}{padding}{value}")

    for label, defs in inlined_sections:
        lines.append("")
        banner_len = max(len(label) + 6, 30)
        lines.append("/* " + "-" * banner_len + " */")
        padding_total = banner_len - len(label)
        left = padding_total // 2
        right = padding_total - left
        lines.append("/* " + " " * left + label + " " * right + " */")
        lines.append("/* " + "-" * banner_len + " */")
        for name, value, desc in defs:
            if desc:
                lines.append(f"/* {desc} */")
            padding = " " * (max_len - len(name) + 2)
            lines.append(f"#define {name}{padding}{value}")

    lines.append("")
    lines.append(f"#endif /* {guard_name} */")
    lines.append("")

    content = "\n".join(lines)

    file_path = os.path.join(outdir, my_rel_path)
    file_dir = os.path.dirname(file_path)
    if file_dir:
        os.makedirs(file_dir, exist_ok=True)
    with open(file_path, "w") as fh:
        fh.write(content)


def generate_headers(
    config: Config,
    outdir: str,
    prefix: str = "CONFIG",
    filename: str = "config.h",
) -> None:
    """Generate a hierarchy of standalone C header files — one per Config level.

    Each Config node in the tree gets its own header file.  Define names
    use a **local prefix** based on the node's own ``name`` attribute, so
    they stay stable regardless of nesting.  Files are standalone — parents
    do not ``#include`` children.  Drivers include only the file they need.

    Only fields with ``read=True`` in their field flags are emitted.
    Child configs (from ``config.children``) provide the hierarchy.

    Args:
        config:   Root config to walk.
        outdir:   Root output directory (created automatically).
        prefix:   Prefix for the root node's defines.
        filename: Filename for each node's header.
    """
    os.makedirs(outdir, exist_ok=True)
    _generate_header_tree(config, outdir, "", filename, prefix)
