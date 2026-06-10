# SPDX-FileCopyrightText: 2026 ETH Zurich, University of Bologna and EssilorLuxottica SAS
#
# SPDX-License-Identifier: Apache-2.0
#
# Authors: Germain Haugou (germain.haugou@gmail.com)

"""Hierarchical timing-accuracy levels.

A timing level is a speed/accuracy budget the user assigns to the whole
platform (``--target "name:timing=<level>"``, also reachable as
``--parameter timing=<level>``) or to a subtree of it
(``--target "name:timing.<component/path>=<level>"`` or
``node.set_timing_level(...)`` from a generator). Models that exist in
several timing flavours resolve their flavour from the level at
generation time instead of being hardcoded per instance.

The level is deliberately part of the target string rather than a
standalone CLI flag: it decides which model flavours get compiled
(router sources, ISS compile flags), so it must reach the build the
same way as any other target qualifier — a target built and run with
the same target string always resolves the same levels.

Three levels are defined, ordered by increasing accuracy:

- ``functional`` — untimed; pure functional simulation, fastest.
- ``timed`` — big-packet timing; whole-transaction latency annotation,
  no contention or back-pressure modeling. This is the default and
  matches the historical behavior of most models.
- ``cycle`` — beat-streaming / cycle-approximate; per-cycle packet
  routing with arbitration and back-pressure.

Resolution is hierarchical: a node uses the level set on itself or on
its nearest ancestor, else the global ``--timing`` value, else
``DEFAULT_LEVEL``. A model that does not implement the requested level
silently uses the nearest one it supports, preferring the closest
*less* accurate level (the knob is a speed budget — a model must never
silently substitute a slower flavour than requested).

Precedence, highest first:

1. explicit per-instance model argument (e.g. ``RouterConfig(kind=...)``,
   ``Iss(timed=...)``)
2. CLI ``timing.`` qualifier on the nearest node
3. generator ``set_timing_level()`` on the nearest node
4. global ``timing`` parameter (``name:timing=<level>`` / ``--parameter``)
5. ``DEFAULT_LEVEL``
"""

FUNCTIONAL = 'functional'
TIMED = 'timed'
CYCLE = 'cycle'

# Ordered by increasing accuracy. The order is what nearest_supported()
# uses to snap a requested level to a supported one.
LEVELS = (FUNCTIONAL, TIMED, CYCLE)

DEFAULT_LEVEL = TIMED

_subtree_levels: dict[str, str] = {}
_consumed_subtree_paths: set[str] = set()


def check_level(level: str):
    """Raise if ``level`` is not a known timing level."""
    if level not in LEVELS:
        raise RuntimeError(
            f"Unknown timing level '{level}'. Known levels: {', '.join(LEVELS)}")


def get_global_level() -> str:
    """Return the platform-wide level, or ``DEFAULT_LEVEL`` if unset.

    The global level is the ``timing`` parameter, normally given inside
    the target string (``--target "name:timing=functional"``) so that it
    reaches the build the same way as the run. It is read from the
    parameter registry, which is populated before the target is
    instantiated.
    """
    import gvrun.parameter
    value = gvrun.parameter.get_parameter_arg_value('timing')
    if value is None:
        return DEFAULT_LEVEL
    check_level(value)
    return value


def set_subtree_levels(values: list[str]):
    """Register per-subtree overrides from ``timing.`` target qualifiers.

    Each entry is ``<component/path>=<level>``, where the path is the
    node path as returned by ``SystemTreeNode.get_path()``. The level
    applies to that node and everything below it (unless a deeper node
    sets its own).
    """
    for prop in values:
        if '=' not in prop:
            raise RuntimeError(
                f"Malformed timing override '{prop}': expected PATH=LEVEL")
        key, value = prop.split('=', 1)
        check_level(value)
        _subtree_levels[key] = value


def get_subtree_level_keys() -> set[str]:
    """Return the set of subtree-override paths submitted so far."""
    return set(_subtree_levels.keys())


def get_consumed_subtree_paths() -> set[str]:
    """Return the set of subtree-override paths consumed by resolution."""
    return set(_consumed_subtree_paths)


def nearest_supported(level: str, supported: list[str]) -> str:
    """Snap ``level`` to the nearest level in ``supported``.

    Picks the most accurate supported level that does not exceed the
    requested one; if the model only has more accurate flavours, the
    least accurate of those is used. Ties therefore always break toward
    less accuracy, keeping the level a reliable speed budget.
    """
    check_level(level)
    if not supported or level in supported:
        return level
    ranks = sorted(LEVELS.index(l) for l in supported)
    rank = LEVELS.index(level)
    below = [r for r in ranks if r < rank]
    if below:
        return LEVELS[below[-1]]
    return LEVELS[ranks[0]]


def resolve_level(node, supported: list[str] | None = None) -> str:
    """Resolve the timing level applying to ``node``.

    Walks ``node`` and its ancestors; the first node carrying a level —
    from a CLI ``timing.`` override on its path, else from
    ``set_timing_level()`` — wins. Falls back to the global level. The
    result is snapped to ``supported`` with :func:`nearest_supported`
    when given.
    """
    level = None
    current = node
    while current is not None:
        path = current.get_path() if hasattr(current, 'get_path') else None
        if path is not None and path in _subtree_levels:
            _consumed_subtree_paths.add(path)
            level = _subtree_levels[path]
            break
        node_level = getattr(current, '_gv_timing_level', None)
        if node_level is not None:
            level = node_level
            break
        if hasattr(current, '_get_parent'):
            current = current._get_parent()
        else:
            current = getattr(current, 'parent', None)

    if level is None:
        level = get_global_level()

    if supported is not None:
        level = nearest_supported(level, supported)

    return level
