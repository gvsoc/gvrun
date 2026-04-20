# SPDX-FileCopyrightText: 2026 ETH Zurich and University of Bologna and EssilorLuxottica SAS
#
# SPDX-License-Identifier: Apache-2.0
#
# Authors: Germain Haugou (germain.haugou@gmail.com)

"""Raw flash section — unstructured data block or fill-remaining."""

from __future__ import annotations

from gvrun.flash import FlashSection, register_section_template
from gvrun.utils import CStruct, CStructParent


@register_section_template("raw")
class RawSection(FlashSection):
    """A raw data section.

    Properties
    ----------
    size : int
        Fixed size in bytes. If -1, fills the remaining flash space.
    file : str
        Path to a file whose contents become the section payload.
    data : bytes
        Initial content (zero-filled if not provided).
    """

    def __init__(self, name: str, size: int | None = None,
                 data: bytes | None = None, file: str | None = None):
        super().__init__(name)
        self.declare_property('size', -1 if size is None else int(size),
            'Section size in bytes (-1 to fill remaining flash space)')
        self.declare_property('file', file or '',
            'Path to a file whose contents fill this section')
        self.declare_property('data', data or b'',
            'Raw initial content')

    def build(self):
        size = self.get_property('size')
        if size is None or size < 0:
            size = self.parent.get_size() - self.get_offset()

        data = self.get_property('data')
        file_path = self.get_property('file')
        if file_path:
            with open(file_path, 'rb') as f:
                data = f.read()

        top = CStructParent('raw', parent=self)
        block = CStruct('data', top)
        block.add_field_array('data', size)
        if data:
            block.set_field('data', data[:size])

    def is_empty(self) -> bool:
        return (not self.get_property('data')
                and not self.get_property('file')
                and self.get_property('size') < 0)

    def get_partition_type(self) -> int:
        return 0x1

    def get_partition_subtype(self) -> int:
        return 0x80
