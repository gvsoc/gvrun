# SPDX-FileCopyrightText: 2026 ETH Zurich and University of Bologna and EssilorLuxottica SAS
#
# SPDX-License-Identifier: Apache-2.0
#
# Authors: Germain Haugou (germain.haugou@gmail.com)

"""Runtime-field marker used by the gvrun tree generator.

A config_tree field annotated as ``Annotated[T, Runtime]`` is excluded
from the compile-time platform tree and instead carried through the JSON
property wire, so its value can be changed at ``gvrun run`` time without
recompiling the platform. The engine overlays the value onto the typed
config struct at component construction.

Kept in gvrun (not in config_tree) because the semantics are specific to
this pipeline; the generic config system stays untouched.
"""

from __future__ import annotations
from typing import Any, get_args


class Runtime:
    """Marker used as a second argument to ``typing.Annotated`` to flag a
    Config field as settable at simulation run time."""


def is_runtime_annotation(type_annotation: Any) -> bool:
    """Return True if ``type_annotation`` is ``Annotated[T, Runtime]``."""
    metadata = getattr(type_annotation, '__metadata__', None)
    if metadata is None:
        return False
    for marker in metadata:
        if marker is Runtime or (isinstance(marker, type) and issubclass(marker, Runtime)):
            return True
    return False


def unwrap_annotated(type_annotation: Any) -> Any:
    """Return the underlying type of ``Annotated[T, ...]``, or the type
    itself if not annotated."""
    if hasattr(type_annotation, '__metadata__'):
        args = get_args(type_annotation)
        if args:
            return args[0]
    return type_annotation
