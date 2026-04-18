# SPDX-FileCopyrightText: 2026 ETH Zurich, University of Bologna and EssilorLuxottica SAS
#
# SPDX-License-Identifier: Apache-2.0
#
# Authors: Germain Haugou (germain.haugou@gmail.com)

"""Parse structured qualifiers from target name strings.

Supports two forms after the target name:

Legacy (bare key=value):
    target:key1=val1,key2=val2

Structured (named qualifiers):
    target:config(chip/nb_cus=2,frequency=100000000):param(size=100)
    target:attr(soc/l2/size=0x20000)

Available qualifiers:
    config  — Override config_tree Config dataclass fields.
    param   — Override build parameters.
    attr    — Override attributes (low-level properties passed to C++ models).
"""

import argparse
import re
from dataclasses import dataclass, field

import gvrun.commands


@dataclass
class ParsedTarget:
    """Result of parsing a target string."""
    name: str
    qualifiers: list[tuple[str, list[str]]] = field(default_factory=list)


def parse_target_string(raw: str) -> ParsedTarget:
    """Parse a target string into name and qualifiers.

    Parameters
    ----------
    raw : str
        The raw target string, e.g. "target:config(chip/nb_cus=2)".

    Returns
    -------
    ParsedTarget
        Parsed target name and qualifier list.
    """
    colon_pos = raw.find(':')
    if colon_pos == -1:
        return ParsedTarget(name=raw)

    name = raw[:colon_pos]
    remainder = raw[colon_pos + 1:]

    if not remainder:
        return ParsedTarget(name=name)

    # Detect structured vs legacy mode
    if re.match(r'[a-zA-Z_]\w*\(', remainder):
        qualifiers = _parse_structured(remainder, raw)
    else:
        # Legacy: bare key=val,key2=val2 → treated as param qualifier
        qualifiers = [('param', remainder.split(','))]

    return ParsedTarget(name=name, qualifiers=qualifiers)


def _parse_structured(remainder: str, raw: str) -> list[tuple[str, list[str]]]:
    """Parse structured qualifier groups like 'config(a=1,b=2):param(c=3)'."""
    qualifiers = []
    pos = 0
    length = len(remainder)

    while pos < length:
        # Extract qualifier name
        paren_pos = remainder.find('(', pos)
        if paren_pos == -1:
            raise RuntimeError(
                f"Malformed target qualifier in '{raw}': expected '(' after "
                f"qualifier name at position {pos}")

        qualifier_name = remainder[pos:paren_pos]
        if not qualifier_name or not re.match(r'^[a-zA-Z_]\w*$', qualifier_name):
            raise RuntimeError(
                f"Malformed target qualifier in '{raw}': invalid qualifier "
                f"name '{qualifier_name}'")

        # Find matching closing paren
        close_pos = remainder.find(')', paren_pos + 1)
        if close_pos == -1:
            raise RuntimeError(
                f"Malformed target qualifier in '{raw}': unclosed parenthesis "
                f"for qualifier '{qualifier_name}'")

        content = remainder[paren_pos + 1:close_pos]
        args = [a for a in content.split(',') if a] if content else []
        qualifiers.append((qualifier_name, args))

        pos = close_pos + 1
        if pos < length:
            if remainder[pos] != ':':
                raise RuntimeError(
                    f"Malformed target qualifier in '{raw}': expected ':' "
                    f"between qualifiers at position {pos}")
            pos += 1

    return qualifiers


# ---------------------------------------------------------------------------
# Qualifier handlers
# ---------------------------------------------------------------------------

def _apply_config_qualifier(values: list[str], args: argparse.Namespace):
    """Route config overrides to Config.override_fields via parse_attribute_arg_values."""
    gvrun.commands.parse_attribute_arg_values(values)


def _apply_param_qualifier(values: list[str], args: argparse.Namespace):
    """Route parameter overrides to args.parameters for later processing."""
    args.parameters.extend(values)


def _apply_attr_qualifier(values: list[str], args: argparse.Namespace):
    """Route attribute overrides to the attribute system (low-level properties for C++ models)."""
    gvrun.commands.parse_attribute_arg_values(values)


QUALIFIER_HANDLERS: dict[str, callable] = {
    'config': _apply_config_qualifier,
    'param': _apply_param_qualifier,
    'attr': _apply_attr_qualifier,
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
            known = ', '.join(sorted(QUALIFIER_HANDLERS))
            raise RuntimeError(
                f"Unknown target qualifier '{qualifier_name}'. "
                f"Known qualifiers: {known}")
        handler(values, args)
