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
Configuration system with dataclass-based configuration and command-line attribute overrides.

This module provides a framework for defining hierarchical configurations using Python
dataclasses. It supports type casting, command-line attribute overrides, and custom
formatting for configuration values.

Key Features:
    - Hierarchical configuration with parent-child relationships
    - Command-line attribute overrides via set_attributes()
    - Type-safe configuration with automatic casting
    - Support for enums, nested dataclasses, lists, sets, tuples, and dicts
    - Custom field metadata (description, format, dump options)
    - Hex formatting with grouping for integer values
"""

# For python 3.12
from __future__ import annotations
import json
import enum
import os
from dataclasses import fields, is_dataclass, dataclass, field
from typing import Any, cast, get_args, get_origin
from dataclasses import MISSING
try:
    from typing import override  # Python 3.12+
except ImportError:
    from typing_extensions import override  # Python 3.10–3.11

__attribute_arg_values: dict[str, str] = {}

def set_attributes(attributes: list[str]) -> None:
    """
    Set configuration attributes from command-line style key=value pairs.

    This function populates the global attribute registry that will be used to override
    configuration field defaults during Config instantiation.

    Args:
        attributes: List of strings in "path/to/field=value" format.
                   The path is hierarchical using '/' separators.

    Example:
        >>> set_attributes([
        ...     "cpu/frequency=1000000",
        ...     "memory/size=0x1000",
        ...     "debug/enabled=true"
        ... ])
    """
    global __attribute_arg_values

    for prop in attributes:
        key, value = prop.split('=', 1)
        __attribute_arg_values[key] = value


@dataclass
class Config:
    """
    Base class for hierarchical configuration dataclasses.

    This class provides automatic path tracking, command-line attribute override support,
    and custom repr formatting based on field metadata.

    Attributes:
        parent: Optional parent Config object for hierarchical path construction.
        name: Name of this configuration node (used in path construction).
        path: Computed hierarchical path (e.g., "parent/child/field").

    The __post_init__ method automatically:
        1. Constructs the hierarchical path based on parent and name
        2. Checks for command-line overrides for each field
        3. Casts and applies override values with proper type conversion

    Example:
        >>> @dataclass
        >>> class CPUConfig(Config):
        ...     frequency: int = 1000000
        ...     cores: int = 4
        >>>
        >>> @dataclass
        >>> class SystemConfig(Config):
        ...     cpu: CPUConfig = cfg_field(default_factory=CPUConfig)
        >>>
        >>> system = SystemConfig(name="system")
        >>> cpu = CPUConfig(parent=system, name="cpu")
    """

    parent: Config | None = field(default=None, repr=False)
    name: str | None = field(default=None, repr=False)
    path: str = field(init=False, repr=False)

    def __post_init__(self):
        """
        Initialize the configuration path and apply command-line attribute overrides.

        This method is automatically called after dataclass __init__. It:
        1. Constructs the hierarchical path from parent path and name
        2. For each field marked with init=True, checks for command-line overrides
        3. Casts override values to the appropriate type and updates the field
        """
        if self.parent is not None and self.name is not None:
            parent_path = self.parent.__get_path()
            if parent_path is not None and parent_path != '':
                self.path = parent_path + '/' + self.name
            else:
                self.path = self.name
        else:
            self.path = ''

        for f in fields(self):
            path = self.__get_path()
            if path is not None:
                path = path + '/' + f.name
            else:
                path = f.name

            if f.init:
                cmd_value = _get_attribute_arg_value(path)
                if cmd_value is not None:
                    casted = _cast_to_type(cmd_value, f.type)
                    setattr(self, f.name, casted)


    def __get_path(self) -> str | None:
        """
        Get the hierarchical path of this configuration node.

        Returns:
            The computed path string (e.g., "parent/child/field").
        """
        return self.path

    @override
    def __repr__(self) -> str:
        """
        Generate a string representation showing fields marked for inlined dump.

        Only fields with metadata inlined_dump=True and repr=True are included.
        Fields with format="hex" are formatted using hex grouping.

        Returns:
            String like "ClassName(field1=value1, field2=0x1234_5678)".
        """
        parts: list[str] = []
        for f in fields(self):
            if f.repr and hasattr(self, f.name):
                if f.metadata.get("inlined_dump") == True:
                    value = getattr(self, f.name)
                    fmt = f.metadata.get("format")

                    if fmt == "hex" and isinstance(value, int):
                        value = _hex_grouped(value)

                    parts.append(f"{f.name}={value}")

        return f"{self.__class__.__name__}({', '.join(parts)})"

    def _collect_defines(self, prefix: str = "CONFIG",
                         section_path: list[str] | None = None,
                         depth: int = 0) -> list[dict]:
        """
        Recursively collect C preprocessor defines from this config tree.

        Walks all dataclass fields. Leaf values (int, bool, str, float, enum) produce a
        ``#define``.  Nested ``Config`` subclasses and lists of ``Config`` are recursed into.
        Fields inherited from the ``Config`` base (parent, name, path) are skipped.

        Args:
            prefix: Underscore-separated prefix for the define name
                    (e.g. ``"CONFIG"`` → ``CONFIG_FREQUENCY``).
            section_path: Hierarchical path of section names for readability.
            depth: Current nesting depth.

        Returns:
            List of entries.  Each entry is either:
            - A leaf: ``{"kind": "define", "name": str, "value": str, "desc": str}``
            - A section: ``{"kind": "section", "label": str, "depth": int,
              "children": list[dict]}``
        """
        if section_path is None:
            section_path = []

        _base_names = {"parent", "name", "path"}
        leaves: list[dict] = []
        sections: list[dict] = []

        for f in fields(self):
            if f.name in _base_names:
                continue

            value = getattr(self, f.name, None)
            if value is None:
                continue

            define_name = f"{prefix}_{f.name.upper()}"
            desc = f.metadata.get("description", "") if f.metadata else ""
            fmt = f.metadata.get("format") if f.metadata else None
            label = f.name.upper().replace("_", " ")

            # Nested Config → recurse into a section
            if isinstance(value, Config):
                children = value._collect_defines(
                    define_name, section_path + [label], depth + 1)
                if children:
                    sections.append({
                        "kind": "section",
                        "label": " / ".join(section_path + [label]),
                        "depth": depth + 1,
                        "children": children,
                    })
                continue

            # List of Configs → recurse with index
            if isinstance(value, (list, tuple)):
                all_config = all(isinstance(v, Config) for v in value)
                if all_config and len(value) > 0:
                    list_children: list[dict] = []
                    list_children.append({
                        "kind": "define",
                        "name": f"{define_name}_COUNT",
                        "value": str(len(value)),
                        "desc": f"Number of {f.name}",
                    })
                    for i, item in enumerate(value):
                        item_label = f"{label} {i}"
                        item_children = item._collect_defines(
                            f"{define_name}_{i}", section_path + [item_label], depth + 1)
                        if item_children:
                            list_children.append({
                                "kind": "section",
                                "label": " / ".join(section_path + [item_label]),
                                "depth": depth + 1,
                                "children": item_children,
                            })
                    sections.append({
                        "kind": "section",
                        "label": " / ".join(section_path + [label]),
                        "depth": depth + 1,
                        "children": list_children,
                    })
                    continue

            # Leaf value → format
            if isinstance(value, bool):
                c_value = "1" if value else "0"
            elif isinstance(value, int):
                if fmt == "hex":
                    c_value = f"0x{value:08x}"
                else:
                    c_value = str(value)
            elif isinstance(value, float):
                c_value = str(value)
            elif isinstance(value, str):
                c_value = f'"{value}"'
            elif isinstance(value, enum.Enum):
                v = value.value
                if isinstance(v, int):
                    c_value = str(v)
                else:
                    c_value = f'"{v}"'
            else:
                continue

            leaves.append({
                "kind": "define",
                "name": define_name,
                "value": c_value,
                "desc": desc,
            })

        # Leaves first (direct fields of this level), then nested sections
        return leaves + sections

    def generate_header(self, path: str, prefix: str = "CONFIG",
                        guard: str | None = None) -> None:
        """
        Generate a C header file with ``#define`` directives from this config tree.

        The header contains an include guard and one ``#define`` per leaf field, with
        optional comments taken from the field description.  Nested Config objects are
        rendered as labeled sections for readability.

        Args:
            path:   Output file path.  Parent directories are created automatically.
            prefix: Prefix for all define names (default ``"CONFIG"``).
            guard:  Include-guard macro name.  If *None*, one is derived from *path*.
        """
        tree = self._collect_defines(prefix)

        if guard is None:
            guard = "_" + os.path.basename(path).upper().replace(".", "_").replace("-", "_") + "_"

        # Collect all define names to compute alignment
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
        lines.append("/* Auto-generated from GVSoC Config tree — do not edit */")

        def _render(entries: list[dict], depth: int) -> None:
            for e in entries:
                if e["kind"] == "section":
                    label = e["label"]
                    d = e["depth"]
                    lines.append("")
                    if d <= 1:
                        # Top-level section: prominent banner
                        banner_len = max(len(label) + 6, 40)
                        lines.append("/* " + "=" * banner_len + " */")
                        padding_total = banner_len - len(label)
                        left = padding_total // 2
                        right = padding_total - left
                        lines.append("/* " + " " * left + label + " " * right + " */")
                        lines.append("/* " + "=" * banner_len + " */")
                    else:
                        # Deeper section: lighter separator
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

    @staticmethod
    def _format_leaf(value: Any, fmt: str | None) -> str | None:
        """Format a leaf value as a C literal string.

        Args:
            value: The Python value to format.
            fmt: Optional format hint (e.g. ``"hex"``).

        Returns:
            The C literal string, or *None* if the type cannot be represented.
        """
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

    def _is_leaf_config(self) -> bool:
        """Return True if this Config has no nested Config children."""
        _base_names = {"parent", "name", "path"}
        for f in fields(self):
            if f.name in _base_names:
                continue
            value = getattr(self, f.name, None)
            if value is None:
                continue
            if isinstance(value, Config):
                return False
            if isinstance(value, (list, tuple)) and value:
                if all(isinstance(v, Config) for v in value):
                    return False
        return True

    def _collect_leaf_defines(self, prefix: str) -> list[tuple[str, str, str]]:
        """Collect defines for a leaf Config (no child Configs).

        Returns:
            List of (define_name, c_value, description) tuples.
        """
        _base_names = {"parent", "name", "path"}
        result: list[tuple[str, str, str]] = []
        for f in fields(self):
            if f.name in _base_names:
                continue
            value = getattr(self, f.name, None)
            if value is None:
                continue
            define_name = f"{prefix}_{f.name.upper()}"
            desc = f.metadata.get("description", "") if f.metadata else ""
            fmt = f.metadata.get("format") if f.metadata else None
            c_value = Config._format_leaf(value, fmt)
            if c_value is not None:
                result.append((define_name, c_value, desc))
        return result

    def _get_local_prefix(self, fallback: str = "CONFIG") -> str:
        """Return the define prefix for this Config node.

        Uses ``CONFIG_<NAME>`` when a name is set, otherwise *fallback*.
        """
        if self.name:
            return f"CONFIG_{self.name.upper()}"
        return fallback

    def _generate_header_tree(self, outdir: str, rel_dir: str,
                              filename: str, fallback_prefix: str = "CONFIG") -> None:
        """Recursively generate one standalone header per Config level.

        Each Config node produces its own self-contained header.  Define names
        use a **local prefix** derived from the node's own ``name`` (e.g.
        ``CONFIG_SOC_*``), so they remain stable regardless of how the Config
        is nested.  Parent headers do **not** ``#include`` children — each
        file is meant to be included independently by the driver that needs it.

        Leaf child Configs (no nested Configs of their own) are inlined into
        the parent's header with a 3-line banner.

        Args:
            outdir:          Root output directory.
            rel_dir:         Relative directory for this node within *outdir*.
            filename:        Filename for this node's header (e.g. ``"config.h"``).
            fallback_prefix: Prefix to use when this node has no name (root).
        """
        prefix = self._get_local_prefix(fallback_prefix)
        my_rel_path = os.path.join(rel_dir, filename) if rel_dir else filename

        _base_names = {"parent", "name", "path"}

        leaf_defines: list[tuple[str, str, str]] = []     # (name, value, desc)
        list_defines: list[tuple[str, str, str]] = []     # (name, value, desc)
        # Inlined leaf sections: (banner_label, [(name, value, desc), ...])
        inlined_sections: list[tuple[str, list[tuple[str, str, str]]]] = []

        for f in fields(self):
            if f.name in _base_names:
                continue

            value = getattr(self, f.name, None)
            if value is None:
                continue

            define_name = f"{prefix}_{f.name.upper()}"
            desc = f.metadata.get("description", "") if f.metadata else ""
            fmt = f.metadata.get("format") if f.metadata else None
            child_dir_name = f.name
            label = f.name.upper().replace("_", " ")

            # Nested Config
            if isinstance(value, Config):
                if value._is_leaf_config():
                    # Inline leaf config with a banner, using parent prefix + field name
                    leaf_defs = value._collect_leaf_defines(define_name)
                    if leaf_defs:
                        inlined_sections.append((label, leaf_defs))
                else:
                    # Non-leaf: recurse into its own file
                    child_rel = os.path.join(rel_dir, child_dir_name)
                    value._generate_header_tree(
                        outdir, child_rel, "config.h", define_name)
                continue

            # List of Configs → recurse with index
            if isinstance(value, (list, tuple)):
                all_config = all(isinstance(v, Config) for v in value)
                if all_config and len(value) > 0:
                    list_defines.append((f"{define_name}_COUNT", str(len(value)),
                                        f"Number of {f.name}"))
                    for i, item in enumerate(value):
                        item_label = f"{label} {i}"
                        item_prefix = f"{define_name}_{i}"
                        if item._is_leaf_config():
                            leaf_defs = item._collect_leaf_defines(item_prefix)
                            if leaf_defs:
                                inlined_sections.append((item_label, leaf_defs))
                        else:
                            child_rel = os.path.join(rel_dir, child_dir_name, str(i))
                            item._generate_header_tree(
                                outdir, child_rel, "config.h", item_prefix)
                    continue

            # Leaf value
            c_value = Config._format_leaf(value, fmt)
            if c_value is not None:
                leaf_defines.append((define_name, c_value, desc))

        # Collect all define names for alignment
        all_names: list[str] = [n for n, _, _ in leaf_defines] + \
                               [n for n, _, _ in list_defines]
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
        lines.append("/* Auto-generated from GVSoC Config tree — do not edit */")

        if leaf_defines or list_defines:
            lines.append("")
            for name, value, desc in leaf_defines:
                if desc:
                    lines.append(f"/* {desc} */")
                padding = " " * (max_len - len(name) + 2)
                lines.append(f"#define {name}{padding}{value}")
            for name, value, desc in list_defines:
                if desc:
                    lines.append(f"/* {desc} */")
                padding = " " * (max_len - len(name) + 2)
                lines.append(f"#define {name}{padding}{value}")

        # Inlined leaf sections with 3-line banner
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

        # Write file
        file_path = os.path.join(outdir, my_rel_path)
        file_dir = os.path.dirname(file_path)
        if file_dir:
            os.makedirs(file_dir, exist_ok=True)
        with open(file_path, "w") as fh:
            fh.write(content)

    def generate_headers(self, outdir: str, prefix: str = "CONFIG",
                         filename: str = "config.h") -> None:
        """Generate a hierarchy of standalone C header files — one per Config level.

        Each Config node in the tree gets its own header file.  Define names
        use a **local prefix** based on the node's own ``name`` attribute, so
        they stay stable regardless of nesting.  Files are standalone — parents
        do not ``#include`` children.  Drivers include only the file they need.

        Args:
            outdir:   Root output directory.  Created automatically.
            prefix:   Prefix for the root node's defines (default ``"CONFIG"``).
            filename: Filename for each node's header (default ``"config.h"``).
        """
        os.makedirs(outdir, exist_ok=True)
        self._generate_header_tree(outdir, "", filename, prefix)

    def generate_cpp_header(self, output_path: str | None = None) -> str:
        """Generate a C++ config struct header from this Config class.

        Parameters
        ----------
        output_path : str, optional
            If provided, write the header to this file.

        Returns
        -------
        str
            The generated C++ header content.
        """
        from gvrun.config_gen import generate_cpp_header
        return generate_cpp_header(type(self), output_path=output_path)

def cfg_field(
    *,
    default: Any = MISSING,
    desc: str = "",
    fmt: str | None = None,
    init: bool = True,
    dump: bool = False,
    inlined_dump: bool = False
) -> Any:
    """
    Create a configuration field with custom metadata.

    This is a wrapper around dataclasses.field() that adds configuration-specific
    metadata for documentation, formatting, and serialization.

    Args:
        default: Default value for the field (same as dataclass field default).
        desc: Human-readable description of the field's purpose.
        fmt: Format string for value display (e.g., "hex" for hexadecimal integers).
        init: Whether this field should be included in __init__ (default: True).
        dump: Whether this field should be included in full dumps.
        inlined_dump: Whether this field should be included in __repr__ output.

    Returns:
        A dataclass field with the specified metadata.

    Example:
        >>> @dataclass
        >>> class MemConfig(Config):
        ...     base_addr: int = cfg_field(
        ...         default=0x80000000,
        ...         desc="Base address of memory region",
        ...         fmt="hex",
        ...         inlined_dump=True
        ...     )
        ...     size: int = cfg_field(
        ...         default=0x10000,
        ...         desc="Size in bytes",
        ...         fmt="hex"
        ...     )
    """
    md: dict[str, object] = {}
    md["description"] = desc
    md["format"] = fmt
    md["dump"] = dump
    md["inlined_dump"] = inlined_dump

    return field(default=default, init=init, metadata=md)


def _get_attribute_arg_value(name: str) -> str | None:
    """
    Retrieve a command-line attribute override value by path.

    Args:
        name: The hierarchical path to the attribute (e.g., "system/cpu/frequency").

    Returns:
        The string value if found, None otherwise.
    """
    return __attribute_arg_values.get(name)

def _hex_grouped(value: int, group: int = 4) -> str:
    """
    Format an integer as a hex string with underscore grouping.

    Args:
        value: The integer value to format.
        group: Number of hex digits per group (default: 4).

    Returns:
        Hex string like "0x8000_0000" or "0x1234_5678_abcd".

    Example:
        >>> _hex_grouped(0x12345678)
        '0x1234_5678'
        >>> _hex_grouped(0xabcdef, group=2)
        '0xab_cd_ef'
    """
    s = f"{value:x}"
    parts = [s[max(i - group, 0):i] for i in range(len(s), 0, -group)]
    return "0x" + "_".join(reversed(parts))

def _parse_bool(s: Any) -> bool:
    """
    Parse a boolean value from various string representations.

    Accepts common boolean representations (case-insensitive):
    - True: "1", "true", "t", "yes", "y", "on"
    - False: "0", "false", "f", "no", "n", "off"

    Args:
        s: Value to parse (string, bool, or other).

    Returns:
        Boolean value.

    Raises:
        ValueError: If the value cannot be parsed as a boolean.

    Example:
        >>> _parse_bool("yes")
        True
        >>> _parse_bool("0")
        False
        >>> _parse_bool(True)
        True
    """
    if isinstance(s, bool):
        return s
    if s is None:
        raise ValueError("Cannot parse bool from None")
    v = str(s).strip().lower()
    if v in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if v in {"0", "false", "f", "no", "n", "off"}:
        return False
    raise ValueError(f"Invalid boolean value: {s!r}")

def _cast_to_type(value: Any, typ: Any) -> Any:
    """
    Cast a CLI-provided value (usually string) to a dataclass field type annotation.

    This function handles complex type annotations including:
    - Generic types: list[T], set[T], tuple[T, ...], dict[K, V]
    - Enums (by name or value)
    - Nested dataclasses (from JSON)
    - Primitives: bool, int, float, str
    - Hex integers with underscores (e.g., "0x8000_0000")

    Args:
        value: The value to cast (typically a string from CLI).
        typ: The target type annotation (can be generic, union, etc.).

    Returns:
        The value cast to the appropriate type.

    Raises:
        ValueError: If casting fails or value format is invalid.
        json.JSONDecodeError: If JSON parsing fails for dict/dataclass types.

    Example:
        >>> _cast_to_type("42", int)
        42
        >>> _cast_to_type("true", bool)
        True
        >>> _cast_to_type("[1,2,3]", list[int])
        [1, 2, 3]
        >>> _cast_to_type("0x1000_0000", int)
        268435456
    """
    if value is None:
        return None

    origin = get_origin(typ)
    args = get_args(typ)

    # list[T], set[T], tuple[T, ...]
    if origin in (list, set, tuple):
        (elem_t,) = args if args else (str,)
        if isinstance(value, str):
            s = value.strip()
            # Support JSON arrays: '[1,2,3]'
            if s.startswith("["):
                items = json.loads(s)
            else:
                # Fallback: comma-separated: '1,2,3'
                items = [x.strip() for x in s.split(",") if x.strip() != ""]
        else:
            items = list(value)

        casted = [_cast_to_type(x, elem_t) for x in items]
        if origin is list:
            return casted
        if origin is set:
            return set(casted)
        return tuple(casted)

    # dict[K, V] (expect JSON)
    if origin is dict:
        if not isinstance(value, str):
            return value
        return json.loads(value)

    # Enums
    if isinstance(typ, type) and issubclass(typ, enum.Enum):
        if isinstance(value, typ):
            return value
        # allow both "NAME" and raw value
        s = str(value)
        try:
            return typ[s]
        except KeyError:
            # try constructor on the enum value
            return typ(_cast_to_type(s, type(next(iter(typ)).value)))

    # Nested dataclass (expect JSON object)
    if isinstance(typ, type) and is_dataclass(typ):
        if isinstance(value, typ):
            return value
        if not isinstance(value, str):
            raise ValueError(f"Expected JSON string for {typ.__name__}, got {type(value)}")
        data = json.loads(value)
        if not isinstance(data, dict):
            raise ValueError(f"Expected JSON object for {typ.__name__}, got {data!r}")
        return typ(**data)

    # Primitives / fallbacks
    if typ is bool:
        return _parse_bool(value)
    if typ is int:
        # supports hex like "0x8000_0000"
        return int(str(value).replace("_", ""), 0)
    if typ is float:
        return float(value)
    if typ is str:
        return str(value)

    # If it's already the right type, keep it
    if isinstance(value, typ):
        return value

    # Last resort: call the type
    return cast(Any, typ(value))
