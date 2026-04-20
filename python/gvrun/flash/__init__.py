# SPDX-FileCopyrightText: 2026 ETH Zurich and University of Bologna and EssilorLuxottica SAS
#
# SPDX-License-Identifier: Apache-2.0
#
# Authors: Germain Haugou (germain.haugou@gmail.com)

"""
Flash image generation framework.

Targets declare flashes (hardware) via :class:`Flash` and may attach a
default content layout (JSON file listing sections and their default
properties). Tests declare content either:

- Imperatively from ``config.py``: ``flash.add_section(SectionClass(...))``
- Declaratively via the default JSON + ``flash.set_property(...)``
  or CLI flags ``--flash-property VALUE@FLASH:SECTION:KEY`` and
  ``--flash-content PATH@FLASH``.

The ``image`` command calls :meth:`Flash.generate_image` to produce binaries.
"""

from __future__ import annotations

import json
import os
from collections import OrderedDict
from prettytable import PrettyTable
from config_tree import Config, cfg_field


class FlashConfig(Config):
    """Config dataclass for declaring a flash in the target's hardware description."""
    size: int = cfg_field(default=0, read=True, desc="Flash size in bytes", fmt="hex")
    flash_type: str = cfg_field(default='', read=True, desc="Flash type (mram, hyper, spi, ...)")
    sector_size: int = cfg_field(default=0x1000, read=True, desc="Sector size in bytes", fmt="hex")


# -----------------------------------------------------------------------------
# Section template registry
# -----------------------------------------------------------------------------

_SECTION_TEMPLATES: dict[str, type] = {}


def register_section_template(name: str):
    """Decorator: register a FlashSection subclass under a short template name.

    The template name is what appears in the JSON layout's ``"template"``
    field and in CLI ``--flash-property`` paths.
    """

    def _decorator(cls):
        _SECTION_TEMPLATES[name] = cls
        return cls

    return _decorator


def get_section_template(name: str) -> type:
    """Look up a registered FlashSection class by template name."""
    cls = _SECTION_TEMPLATES.get(name)
    if cls is None:
        known = ', '.join(sorted(_SECTION_TEMPLATES.keys())) or '(none)'
        raise RuntimeError(f'Unknown flash section template: "{name}". '
                           f'Known templates: {known}')
    return cls


# -----------------------------------------------------------------------------
# Section property system
# -----------------------------------------------------------------------------

class FlashSectionProperty:
    """A single named property on a section, with default value and description."""

    def __init__(self, name: str, value, description: str = ''):
        self.name: str = name
        self.value = value
        self.description: str = description


class FlashSection:
    """Base class for flash sections.

    Subclasses declare typed properties via :meth:`declare_property` in their
    ``__init__``. Property values can be set:

    - Programmatically: :meth:`set_property`
    - From a JSON content entry: :meth:`set_content`
    - From the CLI: ``--flash-property VALUE@FLASH:SECTION:KEY``

    Parameters
    ----------
    name : str
        Section name (e.g. 'readfs', 'app_binary', 'raw').
    """

    def __init__(self, name: str):
        self.name: str = name
        self.section_id: int = 0
        self.parent: Flash | None = None
        self.offset: int = 0
        self.current_offset: int = 0
        self.structs: list = []
        self.size_align: int | None = None
        self.start_align: int | None = None
        self.properties: dict[str, FlashSectionProperty] = {}

    # --- identity / layout -----------------------------------------------

    def get_name(self) -> str:
        return self.name

    def get_id(self) -> int:
        return self.section_id

    def get_flash(self) -> Flash:
        return self.parent

    def get_offset(self) -> int:
        return self.offset

    def get_current_offset(self) -> int:
        return self.current_offset

    def set_offset(self, offset: int):
        """Set the start offset of the section in the flash."""
        if self.start_align is not None:
            offset = (offset + self.start_align - 1) & ~(self.start_align - 1)
        self.offset = offset
        self.current_offset = offset

    def set_alignments(self, start_align: int | None = None, size_align: int | None = None):
        """Set alignment constraints for this section."""
        self.size_align = size_align
        self.start_align = start_align

    def alloc_offset(self, size: int) -> int:
        """Allocate *size* bytes and return the start offset."""
        current = self.current_offset
        self.current_offset += size
        return current

    def align_offset(self, alignment: int) -> int:
        """Align current offset and return the padding size."""
        aligned = (self.current_offset + alignment - 1) & ~(alignment - 1)
        padding = aligned - self.current_offset
        self.current_offset = aligned
        return padding

    def get_size(self) -> int:
        """Return the section size (content + alignment padding)."""
        size = self.current_offset - self.offset
        if self.size_align is not None:
            size = (size + self.size_align - 1) & ~(self.size_align - 1)
        return size

    def add_struct(self, cstruct) -> object:
        """Register a CStruct for binary packing."""
        self.structs.append(cstruct)
        return cstruct

    # --- property system -------------------------------------------------

    def declare_property(self, name: str, value, description: str = ''):
        """Declare a named property with a default value.

        Should be called by subclasses in ``__init__``. The property can then
        be read by the section's :meth:`build` and set via
        :meth:`set_property` or from JSON / CLI.
        """
        self.properties[name] = FlashSectionProperty(name, value, description)

    def has_property(self, name: str) -> bool:
        return name in self.properties

    def get_property(self, name: str):
        prop = self.properties.get(name)
        if prop is None:
            raise RuntimeError(
                f'Unknown property "{name}" on section "{self.name}". '
                f'Known properties: {", ".join(sorted(self.properties.keys())) or "(none)"}')
        return prop.value

    def set_property(self, name: str, value):
        """Set a property's value.

        If the existing value is a list, the new value is appended (matches
        gapy semantics). Otherwise, the value replaces the current one. For
        scalar properties, strings are cast to match the default type.
        """
        prop = self.properties.get(name)
        if prop is None:
            raise RuntimeError(
                f'Unknown property "{name}" on section "{self.name}". '
                f'Known properties: {", ".join(sorted(self.properties.keys())) or "(none)"}')

        if isinstance(prop.value, list):
            prop.value.append(_cast_value(value, element_hint=prop.value))
        else:
            prop.value = _cast_value(value, type_hint=type(prop.value) if prop.value is not None else None)

    def set_content(self, properties: dict):
        """Apply a dict of properties from a JSON content entry."""
        if not properties:
            return
        for key, value in properties.items():
            if isinstance(value, list):
                for elt in value:
                    self.set_property(key, elt)
            else:
                # Scalar — replace rather than append, even if default is a list.
                prop = self.properties.get(key)
                if prop is None:
                    raise RuntimeError(
                        f'Unknown property "{key}" on section "{self.name}"')
                prop.value = value

    def after_parse(self):
        """Hook called by ``Flash.parse_content`` once properties are set.

        Subclasses override this to perform side effects that should happen
        before ``generate_all`` / ``build`` runs — for example, registering
        an ``ExecutableContainer`` on the owning system tree node.
        """

    def get_partition_type(self) -> int:
        """Partition type byte, used by a ``PartitionTableSection``.

        Concrete sections override this. Default is 0xFF (unknown).
        """
        return 0xFF

    def get_partition_subtype(self) -> int:
        """Partition subtype byte, used by a ``PartitionTableSection``.

        Concrete sections override this. Default is 0xFF (unknown).
        """
        return 0xFF

    # --- lifecycle -------------------------------------------------------

    def build(self):
        """Build the section's internal structures.

        Called after the section is added to a flash and its offset is set.
        Subclasses override this to create CStructs and allocate space.
        """

    def finalize(self):
        """Finalize the section after all sections have been laid out.

        Called after all section offsets and sizes are known.
        Useful for fields that reference other sections (e.g. partition tables).
        """

    def get_image(self) -> bytes:
        """Return the binary content of this section, padded to size."""
        result = bytearray()
        for cstruct in self.structs:
            result += cstruct.pack()

        image_len = len(result)
        section_size = self.get_size()
        if image_len < section_size:
            result += bytearray(section_size - image_len)
        elif image_len > section_size:
            raise RuntimeError(
                f'Section "{self.name}" image is too big '
                f'(expected {section_size}, got {image_len})')
        return bytes(result)

    def is_empty(self) -> bool:
        """Return True if this section has no meaningful content."""
        return True

    def dump_table(self, level: int) -> str:
        """Dump section content as a table string."""
        result = ''
        for cstruct in self.structs:
            result += cstruct.dump_table(level)
        return result


def _cast_value(value, type_hint=None, element_hint=None):
    """Best-effort string -> typed value cast using a default for guidance."""
    if not isinstance(value, str):
        return value

    # Choose the target type from either an explicit hint or the element
    # type of a list (use the first element's type as the hint).
    target = type_hint
    if target is None and isinstance(element_hint, list) and len(element_hint) > 0:
        target = type(element_hint[0])

    if target is bool:
        return value.strip().lower() in ("true", "1", "yes", "y")
    if target is int:
        return int(value, 0)
    if target is float:
        return float(value)
    return value


# -----------------------------------------------------------------------------
# Flash
# -----------------------------------------------------------------------------

class Flash:
    """Represents a physical flash memory with sections.

    The target declares flashes (with hardware properties) and may attach a
    default content layout (``default_content_path``). Tests and CLI flags
    then fill in the section properties.

    Parameters
    ----------
    name : str
        Flash name (e.g. 'mram', 'hyperflash').
    size : int
        Flash capacity in bytes.
    attributes : dict, optional
        Hardware attributes (flash_type, sector_size, ...).
    default_content_path : str, optional
        Path to a JSON file describing the default section layout.
    """

    def __init__(self, name: str, size: int, attributes: dict | None = None,
                 default_content_path: str | None = None):
        self.name: str = name
        self.size: int = size
        self.attributes: dict = attributes or {}
        self.sections: list[FlashSection] = []
        self._sections_by_name: dict[str, FlashSection] = {}
        self.workdir: str | None = None
        self._content_dict: dict | None = None
        self._content_parsed: bool = False
        # Back-reference to the SystemTreeNode this flash was registered on.
        # Populated by ``SystemTreeNode.register_flash``. Sections that want
        # to announce themselves to the surrounding system (e.g. an
        # ``app_binary`` section registering an ``ExecutableContainer``) use
        # this.
        self.owner = None

        if default_content_path is not None:
            self._load_content(default_content_path)

    @classmethod
    def from_config(cls, config: FlashConfig, default_content_path: str | None = None) -> Flash:
        """Create a Flash from a FlashConfig dataclass."""
        return cls(
            name=config.name,
            size=config.size,
            attributes={
                'flash_type': config.flash_type,
                'sector_size': config.sector_size,
            },
            default_content_path=default_content_path,
        )

    # --- basic accessors -------------------------------------------------

    def get_name(self) -> str:
        return self.name

    def get_size(self) -> int:
        return self.size

    def get_attribute(self, name: str):
        """Return a flash hardware attribute."""
        return self.attributes.get(name)

    # --- content (JSON layout) -------------------------------------------

    def _load_content(self, path: str):
        with open(path, 'rb') as f:
            self._content_dict = json.load(f, object_pairs_hook=OrderedDict)

    def set_content(self, content: dict | str):
        """Replace the full content description.

        ``content`` may be a dict (already parsed) or a path to a JSON file.
        Called by ``--flash-content PATH@FLASH``.
        """
        if isinstance(content, str):
            self._load_content(content)
        else:
            self._content_dict = content
        # Any previously-materialised sections are invalidated.
        self.sections = []
        self._sections_by_name = {}
        self._content_parsed = False

    def set_property(self, section_name: str, key: str, value):
        """Override a property for a named section in the default content.

        Appends for list-typed properties, replaces for scalars. Called by
        ``--flash-property VALUE@FLASH:SECTION:KEY``.
        """
        if self._content_dict is None:
            raise RuntimeError(
                f'Flash "{self.name}" has no default content layout; cannot '
                f'set property "{section_name}:{key}". Either provide a '
                f'default_content_path when registering the flash, or use '
                f'flash.add_section() imperatively.')

        for entry in self._content_dict.get('sections', []):
            if entry.get('name') == section_name:
                props = entry.setdefault('properties', {})
                existing = props.get(key)
                if isinstance(existing, list):
                    existing.append(value)
                else:
                    props[key] = value
                # Content changed — force a re-parse before image generation.
                self._content_parsed = False
                self.sections = []
                self._sections_by_name = {}
                return

        names = [e.get('name') for e in self._content_dict.get('sections', [])]
        raise RuntimeError(
            f'Section "{section_name}" not found in flash "{self.name}" '
            f'content. Known sections: {", ".join(names) or "(none)"}')

    def parse_content(self):
        """Instantiate sections from ``_content_dict`` if any.

        Idempotent. Called automatically by the ``image`` / ``flash_layout``
        commands after CLI overrides are applied.
        """
        if self._content_parsed:
            return
        self._content_parsed = True

        if self._content_dict is None:
            return

        # Sections already added imperatively via add_section() are kept; we
        # append the JSON-described ones after them.
        for entry in self._content_dict.get('sections', []):
            template = entry.get('template')
            name = entry.get('name')
            if template is None or name is None:
                raise RuntimeError(
                    f'Invalid flash content entry in flash "{self.name}": '
                    f'each section must have "name" and "template" fields')

            if name in self._sections_by_name:
                # Already present from imperative add_section — skip.
                continue

            cls = get_section_template(template)
            section = cls(name=name)
            section.set_content(entry.get('properties', {}))
            self.add_section(section)

        for section in self.sections:
            section.after_parse()

    # --- imperative section API ------------------------------------------

    def add_section(self, section: FlashSection):
        """Add a section to this flash.

        Sections are laid out in the order they are added.
        """
        if section.name in self._sections_by_name:
            raise RuntimeError(
                f'Duplicate flash section name "{section.name}" in flash "{self.name}"')
        section.section_id = len(self.sections)
        section.parent = self
        self.sections.append(section)
        self._sections_by_name[section.name] = section

    def get_section(self, name: str) -> FlashSection | None:
        """Get a section by name."""
        return self._sections_by_name.get(name)

    def get_sections(self) -> list[FlashSection]:
        """Return all sections."""
        return list(self.sections)

    def is_empty(self) -> bool:
        """Return True if all sections are empty."""
        self.parse_content()
        return all(s.is_empty() for s in self.sections)

    # --- image generation ------------------------------------------------

    def generate_image(self, workdir: str):
        """Lay out sections, build content, and write the binary image.

        Parameters
        ----------
        workdir : str
            Directory where the image file will be written.
        """
        self.parse_content()
        self.workdir = workdir

        if not self.sections:
            return

        # Alignment from flash attributes
        start_align = self.attributes.get('section_start_align')
        size_align = self.attributes.get('section_size_align')

        # Phase 1: compute offsets
        offset = 0
        for section in self.sections:
            section.set_alignments(start_align, size_align)
            section.set_offset(offset)
            section.build()
            offset = section.get_offset() + section.get_size()
            if offset > self.size:
                raise RuntimeError(
                    f'Section "{section.get_name()}" overflows flash "{self.name}": '
                    f'flash size is 0x{self.size:x}, content needs 0x{offset:x}')

        # Phase 2: finalize (cross-section references)
        for section in self.sections:
            section.finalize()

        # Phase 3: write binary
        image = self._pack()
        os.makedirs(workdir, exist_ok=True)
        image_path = os.path.join(workdir, self.name + '.bin')
        with open(image_path, 'wb') as f:
            f.write(image)

    def _pack(self) -> bytes:
        """Pack all sections into a contiguous binary."""
        result = bytearray()
        prev_end = 0
        for section in self.sections:
            # Insert padding for gaps between sections
            gap = section.get_offset() - prev_end
            if gap > 0:
                result += bytearray(gap)
            result += section.get_image()
            prev_end = section.get_offset() + section.get_size()
        return bytes(result)

    def get_image_path(self) -> str | None:
        """Return the path of the generated image file."""
        if self.workdir is None:
            return None
        return os.path.join(self.workdir, self.name + '.bin')

    def dump_layout(self, level: int = 0):
        """Print the flash layout as a table."""
        self.parse_content()
        if not self.sections:
            print(f'\nFlash {self.name}: no sections')
            return

        print(f'\nLayout for flash: {self.name} (size: 0x{self.size:x})')

        table = PrettyTable()
        names = ['Offset', 'Name', 'Size']
        if level > 0:
            names.append('Content')
        table.field_names = names

        for section in self.sections:
            row = [f'0x{section.get_offset():x}', section.get_name(),
                   f'0x{section.get_size():x}']
            if level > 0:
                row.append(section.dump_table(level - 1))
            table.add_row(row)

        table.align = 'l'
        print(table)


# Import the built-in section subpackage so each section class registers
# itself in ``_SECTION_TEMPLATES`` before any descriptor is parsed. This
# import lives at the bottom of the module to break the circular dependency
# (section modules import ``FlashSection`` / ``register_section_template``
# from this module).
from gvrun.flash import sections  # noqa: E402,F401

