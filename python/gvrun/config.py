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
