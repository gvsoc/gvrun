# SPDX-FileCopyrightText: 2026 ETH Zurich and University of Bologna and EssilorLuxottica SAS
#
# SPDX-License-Identifier: Apache-2.0
#
# Authors: Germain Haugou (germain.haugou@gmail.com)

"""Partition table section — index of the sections that follow it.

Consumers (e.g. PMSIS's ``pi_partition_table_load`` / ``pi_fs_mount``)
expect this layout:

- 4 bytes at the very start of the flash: little-endian offset pointing to
  the partition table header (see ``flash_partition.c``).
- At that offset, a 32-byte header (magic 0x02BA, format version, nb
  entries, ...).
- N * 32-byte entries (magic 0x01BA, type, subtype, offset, size, 16-byte
  label, flags).

This section includes the leading 4-byte self-pointer, so placing it as the
first section of a flash makes PMSIS discover it correctly.

Ported from the legacy gapy ``PartitionTableSection``.
"""

from __future__ import annotations

from gvrun.flash import FlashSection, register_section_template
from gvrun.utils import CStruct, CStructParent


_PARTITION_TABLE_HEADER_MAGIC = 0x02BA
_PARTITION_ENTRY_MAGIC = 0x01BA
_PARTITION_TABLE_FORMAT_VERSION = 1


@register_section_template("partition_table")
class PartitionTableSection(FlashSection):
    """Partition table — describes every subsequent section.

    Must be the first section in the flash. Its size is a fixed function of
    the number of sections that follow (one 32-byte header + one 32-byte
    entry per section).
    """

    def __init__(self, name: str):
        super().__init__(name)
        self._followers: list[FlashSection] = []
        self._pointer: CStruct | None = None
        self._header: CStruct | None = None
        self._entries: list[CStruct] = []

    def build(self):
        # Capture the sections that come after this one in the flash.
        flash = self.get_flash()
        all_sections = flash.get_sections()
        idx = all_sections.index(self)
        self._followers = all_sections[idx + 1:]

        top = CStructParent('partition_table', parent=self)
        # 4-byte pointer at the very start of the flash, read by PMSIS to
        # discover the real header.
        self._pointer = CStruct('pointer', top)
        self._pointer.add_field('table_offset', 'I')

        self._header = _make_header(top)
        self._entries = [_make_entry(top, i) for i, _ in enumerate(self._followers)]

    def finalize(self):
        if self._header is None:
            return

        # Point at the partition table header, which sits right after the
        # 4-byte pointer at the start of this section.
        self._pointer.set_field('table_offset', self._header.get_offset())

        self._header.set_field('magic_number', _PARTITION_TABLE_HEADER_MAGIC)
        self._header.set_field('partition_table_version', _PARTITION_TABLE_FORMAT_VERSION)
        self._header.set_field('nb_entries', len(self._followers))

        for entry, section in zip(self._entries, self._followers):
            entry.set_field('magic_number', _PARTITION_ENTRY_MAGIC)
            entry.set_field('type', section.get_partition_type())
            entry.set_field('subtype', section.get_partition_subtype())
            entry.set_field('offset', section.get_offset())
            entry.set_field('size', section.get_size())
            entry.set_field('name', section.get_name().encode('utf-8') + b'\x00')

    def is_empty(self) -> bool:
        flash = self.get_flash()
        if flash is None:
            return True
        all_sections = flash.get_sections()
        try:
            idx = all_sections.index(self)
        except ValueError:
            return True
        # The table is only meaningful if at least one following section has
        # content to advertise.
        for section in all_sections[idx + 1:]:
            if not section.is_empty():
                return False
        return True


def _make_header(parent: CStructParent) -> CStruct:
    hdr = CStruct('header', parent)
    hdr.add_field('magic_number', 'H')
    hdr.add_field('partition_table_version', 'B')
    hdr.add_field('nb_entries', 'B')
    hdr.add_field('crc', 'B')
    hdr.add_field_array('padding', 11)
    hdr.add_field_array('md5', 16)
    return hdr


def _make_entry(parent: CStructParent, index: int) -> CStruct:
    entry = CStruct(f'entry_{index}', parent)
    entry.add_field('magic_number', 'H')
    entry.add_field('type', 'B')
    entry.add_field('subtype', 'B')
    entry.add_field('offset', 'I')
    entry.add_field('size', 'I')
    entry.add_field_array('name', 16)
    entry.add_field('flags', 'I')
    return entry
