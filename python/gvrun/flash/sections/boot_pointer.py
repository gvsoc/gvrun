# SPDX-FileCopyrightText: 2026 ETH Zurich and University of Bologna and EssilorLuxottica SAS
#
# SPDX-License-Identifier: Apache-2.0
#
# Authors: Germain Haugou (germain.haugou@gmail.com)

"""Boot pointer section — the four bytes PMSIS reads to find the partition table.

``__pi_fs_get_fs_flash_opened`` (``pulpos/core/kernel/fs/fs.c``) reads a
little-endian offset from the first four bytes of the flash and mounts the
partition table it points at. On a chip that boots from flash those bytes are
the boot image header's ``next_section`` field, so a real boot section supplies
them and this one is not needed.

A platform with no boot image in its flash -- pulp-open, whose application is
placed by the ELF loader -- has nothing to write them, so it puts this section
first instead. It is only the pointer, with none of a boot header around it.

Like the partition table it describes nothing of its own, so it counts as empty
while every section behind it is empty; a flash with no content stays without
an image.
"""

from __future__ import annotations

from gvrun.flash import FlashSection, register_section_template
from gvrun.utils import CStruct, CStructParent


@register_section_template("boot_pointer")
class BootPointerSection(FlashSection):
    """Four bytes holding the offset of the section that follows."""

    def __init__(self, name: str):
        super().__init__(name)
        self._header: CStruct | None = None

    def build(self):
        top = CStructParent('boot_pointer', parent=self)
        self._header = CStruct('header', top)
        self._header.add_field('next_section', 'I')

    def finalize(self):
        if self._header is None:
            return

        following = self.get_next_section()
        offset = (following.get_offset() if following is not None
                  else self.get_offset() + self.get_size())
        self._header.set_field('next_section', offset)

    def is_empty(self) -> bool:
        flash = self.get_flash()
        if flash is None:
            return True
        sections = flash.get_sections()
        try:
            index = sections.index(self)
        except ValueError:
            return True
        return all(section.is_empty() for section in sections[index + 1:])
