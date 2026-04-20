# SPDX-FileCopyrightText: 2026 ETH Zurich, University of Bologna and EssilorLuxottica SAS
#
# SPDX-License-Identifier: Apache-2.0
#
# Authors: Germain Haugou (germain.haugou@gmail.com)

"""Parse structured qualifiers from target name strings.

Syntax after the target name: ``qualifier.KEY=VALUE`` entries separated by
colons. Chosen for shell-friendliness — no parentheses to quote.

    target:attr.chip/cluster/has_redmule=true
    target:config.chip/nb_cus=2
    target:attr.soc/l2/size=0x20000:config.chip/nb_cus=2

One key=value per qualifier; repeat the qualifier to set multiple keys.

Bare form (no qualifier prefix) is accepted as a shortcut for
``--parameter`` and supports comma-separated multi-key lists — kept for
backward compatibility with existing Makefile-driven tests that build
the target string by joining options. It feeds the same parameter
registry as ``--parameter``, so it is matched against declared
``TargetParameter`` / ``BuildParameter`` / ``ArchParameter`` instances:

    target:access_type=rw,synchronous=false,target_bw=4
      == --parameter access_type=rw --parameter synchronous=false \\
         --parameter target_bw=4

Available qualifiers:
    config  — Override fields on the target's top ``config_tree.Config``.
    attr    — Override per-component attributes (Config-backed or legacy
              ``Value``/``Tree``).
"""

import argparse
import re
from dataclasses import dataclass, field

from config_tree import Config

import gvrun.attribute
import gvrun.commands


@dataclass
class ParsedTarget:
    """Result of parsing a target string."""
    name: str
    qualifiers: list[tuple[str, list[str]]] = field(default_factory=list)


_QUALIFIER_NAME_RE = re.compile(r'^[a-zA-Z_]\w*$')


def parse_target_string(raw: str) -> ParsedTarget:
    """Parse a target string into name and qualifiers.

    Parameters
    ----------
    raw : str
        The raw target string, e.g. ``"target:config.chip/nb_cus=2"``.

    Returns
    -------
    ParsedTarget
        Parsed target name and qualifier list.
    """
    parts = raw.split(':')
    name = parts[0]

    qualifiers: list[tuple[str, list[str]]] = []
    for segment in parts[1:]:
        if not segment:
            continue

        # Distinguish "qualifier.KEY=VALUE" from the bare form
        # "KEY=VALUE[,KEY=VALUE...]". The bare form is backward-compat
        # sugar for the attr qualifier with comma-separated multi-key
        # support. We detect it by checking whether the part before any
        # '.' looks like a qualifier name (identifier-only). The first
        # KEY of a bare form can contain '/' which rules out the
        # qualifier-dot form.
        is_bare = True
        if '.' in segment:
            head, _ = segment.split('.', 1)
            if _QUALIFIER_NAME_RE.match(head) and head in QUALIFIER_HANDLERS:
                is_bare = False

        if is_bare:
            if '=' not in segment:
                raise RuntimeError(
                    f"Malformed target qualifier '{segment}' in '{raw}': "
                    f"expected 'name.KEY=VALUE' (e.g. "
                    f"'attr.chip/cluster/foo=true') or a bare "
                    f"'KEY=VALUE[,KEY=VALUE...]' list")
            bare_values: list[str] = []
            for kv in segment.split(','):
                kv = kv.strip()
                if not kv:
                    continue
                if '=' not in kv:
                    raise RuntimeError(
                        f"Malformed bare target qualifier entry '{kv}' in "
                        f"'{raw}': expected KEY=VALUE")
                bare_values.append(kv)
            if bare_values:
                qualifiers.append(('__bare__', bare_values))
            continue

        qualifier_name, rest = segment.split('.', 1)
        if '=' not in rest:
            raise RuntimeError(
                f"Malformed target qualifier '{segment}' in '{raw}': "
                f"expected a KEY=VALUE pair after '{qualifier_name}.'")
        qualifiers.append((qualifier_name, [rest]))

    return ParsedTarget(name=name, qualifiers=qualifiers)


# ---------------------------------------------------------------------------
# Qualifier handlers — each targets exactly one subsystem so overrides can't
# accidentally land somewhere unintended.
# ---------------------------------------------------------------------------

def _apply_config_qualifier(values: list[str], args: argparse.Namespace):
    """Override fields on the target's ``config_tree.Config`` tree only."""
    Config.override_fields(values)
    gvrun.commands.track_config_overrides(values)


def _apply_attr_qualifier(values: list[str], args: argparse.Namespace):
    """Override component attributes only.

    Feeds both component-attribute registries:

    - ``gvrun.systree`` — read by ``Component.__init__`` (gvrun2) for
      ``<component_path>/<field>`` overrides of fields supplied through a
      ``config_tree.Config`` attached via ``config=...``. This is the path
      that reaches the C++ model via ``add_property``.
    - ``gvrun.attribute`` — read by ``Value.__init__`` for legacy
      ``Tree``/``Value`` hierarchies (e.g. ``PulpOpenAttr``,
      ``ClusterArch``).
    """
    import gvrun.systree
    gvrun.systree.set_attributes(values)
    gvrun.attribute.set_attributes(values)


def _apply_bare_qualifier(values: list[str], args: argparse.Namespace):
    """Route bare ``key=value`` entries to ``--parameter``.

    Appends to ``args.parameters`` so the later ``parse_parameter_arg_values``
    pass picks them up; lands in the same registry consulted by
    ``TargetParameter`` / ``BuildParameter`` / ``ArchParameter`` lookups.
    """
    args.parameters.extend(values)


QUALIFIER_HANDLERS: dict[str, callable] = {
    'config': _apply_config_qualifier,
    'attr': _apply_attr_qualifier,
}

# Internal-only handler used when parse_target_string recognises the
# legacy bare form. Not exposed as a valid user-facing qualifier name
# (names starting with '__' can't be typed on a CLI anyway).
_INTERNAL_HANDLERS: dict[str, callable] = {
    '__bare__': _apply_bare_qualifier,
}


def apply_target_qualifiers(parsed: ParsedTarget, args: argparse.Namespace):
    """Dispatch each qualifier to its handler.

    Parameters
    ----------
    parsed : ParsedTarget
        The parsed target with qualifiers.
    args : argparse.Namespace
        The CLI argument namespace (modified in place for param qualifiers).
    """
    for qualifier_name, values in parsed.qualifiers:
        handler = QUALIFIER_HANDLERS.get(qualifier_name)
        if handler is None:
            handler = _INTERNAL_HANDLERS.get(qualifier_name)
        if handler is None:
            known = ', '.join(sorted(QUALIFIER_HANDLERS))
            raise RuntimeError(
                f"Unknown target qualifier '{qualifier_name}'. "
                f"Known qualifiers: {known}")
        handler(values, args)
