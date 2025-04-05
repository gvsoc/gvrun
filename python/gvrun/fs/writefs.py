"""Provides section template for readfs, to generate a readfs image"""

# Copyright (C) 2022 GreenWaves Technologies
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

#
# Authors: Antoine Faravelon,
#       GreenWaves Technologies (antoine.faravelon@greenwaves-technologies.com)
#



import os.path
import dataclasses
from gapylib.flash import FlashSection, Flash
from gapylib.utils import CStruct, CStructParent



@dataclasses.dataclass
class WriteFsHeader(CStruct):
    """
    Class for generating a WriteFS file header.
    This header is used for block chaining, in a malloc like way.

    Attributes
    ----------
    name : str
        Name of this sub-section.

    parent : str
        Parent, which is aggregating all readfs sub-sections.

    size : int
        size of the block/file.
    """
    def __init__(self, name: str, parent: CStructParent, size: int, align: int):
        super().__init__(name, parent)

        # Magic value for the header
        self.add_field('magic', 'H')
        # Flags of the header (valid / empty)
        self.add_field('flags', 'H')
        # CRC of the payload
        self.add_field('crc', 'I')
        # size of the payload
        self.add_field('size', 'I')
        # Pointer to next block in flash
        self.add_field('next', 'I')
        self.add_field_array('name', 24)
        # Timestamp useable by app code
        self.add_field_array('timestamp', 8)
        header_size_align = (48 + align - 1) & ~(align - 1)
        self.add_field_array('padding', header_size_align - 48)
        # Actual payload (data) align the overall size via payload alignment
        size_align = (size + align - 1) & ~(align - 1)
        self.add_field_array('payload', size_align)
        self.set_field('size',size_align)

class WriteFsSection(FlashSection):
    """
    Class for generating a readfs section.

    Attributes
    ----------
    parent: gapylib.flash.Flash
        Name of the section.
    name : str
        Name of the section.
    section_id : int
        Id of the section.
    """

    def __init__(self, parent: Flash, name, section_id: int):
        super().__init__(parent, name, section_id)

        self.file_paths = []
        self.file_headers = []
        self.files = []
        self.top_struct = None
        self.header = None

        self.declare_property(name='files', value=[],
            description="List of files to be included in the ReadFS."
        )


    def set_content(self, offset: int, content_dict: dict):
        """Set the content of the section.

        Parameters
        ----------
        offset : int
            Starting offset of the section.
        content_dict : dict
            Content of the section
        """
        super().set_content(offset, content_dict)

        # Get the list of files from the properties and determine basenames from the path, which
        # will be used as name in the readfs
        if content_dict.get('properties').get('files') is not None:
            for file in content_dict.get('properties').get('files'):
                self.file_paths.append([os.path.basename(file), file])
        else:
            return

        # First declare the sub-sections so that the right offsets are computed

        # Top structure which will gather all sub-sections
        self.top_struct = CStructParent('writefs', parent=self)

        # Size is a string to be converted if it comes from command-line
        size = self.get_property('size')
        if isinstance(size, str):
            size = int(size, 0)
        if size == -1:
            size = self.parent.get_size() - self.get_offset()

        self.size_align = size

        base = self.get_offset()
        # One header per file containig file size, name and flash offset
        if len(self.file_paths) > 0:
            for i, path in enumerate(self.file_paths):
                filename, filepath = path
                align = self.size_align
                real_size = (os.path.getsize(filepath) + align - 1) & ~(align-1)
                file_header = WriteFsHeader(f'file{i} header', align=align,
                    parent=self.top_struct, size=real_size)
                self.file_headers.append(file_header)
                file_header.set_field('size', real_size)
                file_header.set_field('magic', 0x3f9b)
                # Set as valid,not empty, no crc
                file_header.set_field('flags', 0x1)
                file_header.set_field('crc', 0x0)
                file_header.set_field('name', filename.encode('utf-8') + bytes([0]))
                file_header.set_field('timestamp', i.to_bytes(8,'little'))
                # Per-file content
                with open(filepath, 'rb') as file_desc:
                    file_header.set_field('payload', file_desc.read())

            for i, file_header in enumerate(self.file_headers):
                if i+1 < len(self.file_headers):
                    next_offset = self.file_headers[i+1].get_offset() - base
                    file_header.set_field('next', next_offset)
        else:
            return

        # size align is the "real size" whereas get_size takes properties into
        # account
        size = self.current_offset - self.offset
        if size < self.get_size():
            free_section_size = self.get_size() - size
            free_section_offset = 0
            if free_section_size > 128:
                align = self.size_align
                real_size = (free_section_size) - ((48+align -1)& ~(align-1))
                file_header = WriteFsHeader('free header',
                    parent=self.top_struct,
                                            size=real_size,
                                            align = self.size_align)
                self.file_headers.append(file_header)
                free_section_offset = file_header.get_offset() - base
                file_header.set_field('next', 0xffffffff)
                # free section size, minus header size
                file_header.set_field('magic', 0x3f9b)
                # valid + empty, no crc
                file_header.set_field('flags', 0x3)

            # add an empty section at the end, and link last block to it
            if len(self.file_headers) > 1:
                last_file = self.file_headers[len(self.file_headers) - 2]
                last_file.set_field('next', free_section_offset)
        else:
            if len(self.file_headers) > 0:
                last_file = self.file_headers[len(self.file_headers) - 1]
                last_file.set_field('next', 0xffffffff)


    def is_empty(self) -> bool:
        return len(self.file_paths) == 0

    def get_partition_type(self) -> int:
        return 0x1

    def get_partition_subtype(self) -> int:
        return 0x83
