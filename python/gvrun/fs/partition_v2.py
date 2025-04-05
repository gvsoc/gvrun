"""Provides section template for flash partitions second version"""

#
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
# Authors: Germain Haugou, GreenWaves Technologies (germain.haugou@greenwaves-technologies.com)
# Antoine Faravelon, GreenWaves Technologies (antoine.faravelon@greenwaves-technologies.com)
#


import dataclasses
from gapylib.flash import FlashSection
from gapylib.utils import CStruct, CStructParent, compute_crc

@dataclasses.dataclass
class PartitionTableV2Header(CStruct):
    """
    Class for generating partition table sub-section containing the main header.
    This header contains global information like number of partitions.

    Attributes
    ----------
    name : str
        Name of this sub-section.

    parent : str
        Parent, which is aggregating all sub-sections.
    """
    def __init__(self, name: str, parent: CStructParent):
        super().__init__(name, parent)

        # Magic number
        self.add_field('magic_number', 'H')
        # Partition table version
        self.add_field('partition_table_version', 'B')
        # Number of sections
        self.add_field('nb_entries', 'B')
        # 1 if MD5 sum of sections is enabled
        self.add_field('nb_entries_max', 'B')
        self.add_field('flags', 'H')
        # MD5 sum of all the sections
        self.add_field('crc_table', 'I')
        self.add_field('crc_header', 'I')
        self.add_field('padding', 'B')

    def get_crc(self) -> int:
        """ Compute and return this header's CRC

        Returns
        -------
        int
            CRC of this header
        """
        crc = 0xFFFFFFFF
        byte_fields = self.get_field('magic_number').get_bytes()
        byte_fields += self.get_field('partition_table_version').get_bytes()
        byte_fields += self.get_field('nb_entries').get_bytes()
        byte_fields += self.get_field('nb_entries_max').get_bytes()
        byte_fields += self.get_field('flags').get_bytes()
        byte_fields += self.get_field('crc_table').get_bytes()
        crc = compute_crc(crc, byte_fields)
        return crc

    def get_fields(self) -> bytes:
        """ Compute and return this header's CRC

        Returns
        -------
        int
            CRC of this header
        """
        byte_fields = self.get_field('magic_number').get_bytes()
        byte_fields += self.get_field('partition_table_version').get_bytes()
        byte_fields += self.get_field('nb_entries').get_bytes()
        byte_fields += self.get_field('nb_entries_max').get_bytes()
        byte_fields += self.get_field('flags').get_bytes()
        byte_fields += self.get_field('crc_table').get_bytes()
        byte_fields += self.get_field('crc_header').get_bytes()
        byte_fields += self.get_field('padding').get_bytes()
        return byte_fields


@dataclasses.dataclass
class PartitionTableSectionHeader(CStruct):
    """
    Class for generating partition table sub-section containing a section header.
    This header contains section information like size.

    Attributes
    ----------
    name : str
        Name of this sub-section.

    parent : str
        Parent, which is aggregating all readfs sub-sections.
    """
    def __init__(self, name: str, parent: CStructParent):
        super().__init__(name, parent)

        # Magic number
        self.add_field('uuid', 'H')
        # Partition type
        self.add_field('type', 'B')
        # Partition subtype
        self.add_field('subtype', 'B')
        # Attributes of the partition
        self.add_field('flags', 'H')
        # Type of the flash on which partition is
        self.add_field('flash_type','B')
        # ITF of the flash on which partition is
        self.add_field('itf', 'B')
        # CS of the flash on which the partition is
        self.add_field('cs', 'B')
        # Offset of the partition in the flash
        self.add_field('offset', 'I')
        # Used size in the partition
        self.add_field('size', 'I')
        # Size of the partition in the flash
        self.add_field('max_size', 'I')
        self.add_field('crc_payload', 'I')
        self.add_field_array('padding', 7)
        self.set_field('padding',bytes(7))

    def append_fields(self) -> bytes:
        """ Pack this section's fields in a bytes object

        Returns
        -------
        bytes
            Packed bytefield of the payload
        """
        byte = bytes(0)
        byte += self.get_field('uuid').get_bytes()
        byte += self.get_field('type').get_bytes()
        byte += self.get_field('subtype').get_bytes()
        byte += self.get_field('flags').get_bytes()
        byte += self.get_field('flash_type').get_bytes()
        byte += self.get_field('itf').get_bytes()
        byte += self.get_field('cs').get_bytes()
        byte += self.get_field('offset').get_bytes()
        byte += self.get_field('size').get_bytes()
        byte += self.get_field('max_size').get_bytes()
        byte += self.get_field('crc_payload').get_bytes()
        byte += self.get_field('padding').get_bytes()
        return byte

class PartitionTableSectionV2(FlashSection):
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

    def __init__(self, parent, name: str, section_id: int):
        super().__init__(parent, name, section_id)

        self.section_headers = []
        self.top_struct = None
        self.header = None
        self.sections = []
        self.diff = 0


    def get_partition_type(self)-> int:
        """Return the partition type.

        This information can be used by the partition table as the type.
        This method returns an unknown type (0xff) and should be overloaded by real sections.

        Returns
        -------
        int
            The partition type.
        """
        return 0x2

    def get_partition_subtype(self)-> int:
        """Return the partition subtype.

        This information can be used by the partition table as the subtype.
        This method returns an unknown type (0xff) and should be overloaded by real sections.

        Returns
        -------
        int
            The partition type.
        """
        return 0xe0




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

        # Get all the sections after the partition table to include them in the table
        for _, flash in self.get_flash().get_target().flashes.items():
            self.sections += flash.get_sections()

        # First declare the sub-sections so that the right offsets are computed

        # Top structure which will gather all sub-sections
        self.top_struct = CStructParent('partition table v2', parent=self)

        # Main header for readfs size and number of files
        self.header = PartitionTableV2Header('header', parent=self.top_struct)
        size = len(self.header.get_fields())

        # One header per section
        section_size = 0
        for i, __ in enumerate(self.sections):
            section_header = PartitionTableSectionHeader(f'section{i} header',
                                                         parent=self.top_struct)
            size += len(section_header.append_fields())
            section_size = len(section_header.append_fields())
            self.section_headers.append(section_header)
        request_size = self.get_property('size')
        if request_size is not None and size < request_size:
            self.diff = (request_size - size) // section_size
            for i in range(self.diff):
                section_header = PartitionTableSectionHeader(f'placeholder{i}',
                                                         parent=self.top_struct)
                size += len(section_header.append_fields())
                section_size = len(section_header.append_fields())
                self.section_headers.append(section_header)




    def finalize(self):
        """Finalize the section.

        This can be called to set internal section fields which requires some knowledge of the
        offset or size of other sections.
        The structure of the section should not be changed in this step
        """
        super().finalize()

        # Now that the offsets have been computed, we can fill-in the various fields

        # Get all the sections to include them in the table
        sections = self.sections

        # Main header
        self.header.set_field('magic_number', 0x02BA)
        self.header.set_field('partition_table_version', 2)
        self.header.set_field('nb_entries', len(sections))
        self.header.set_field('nb_entries_max', len(sections) + self.diff)

        # Per-section header
        byte_field = bytes(0)
        for section_id, section in enumerate(self.section_headers):
            if section_id < len(sections):
                section.set_field('uuid', section_id)
                section.set_field('type', sections[section_id].get_partition_type())
                section.set_field('subtype', sections[section_id].get_partition_subtype())
                section.set_field('offset', sections[section_id].get_offset())
                section.set_field('itf', sections[section_id].get_flash().get_itf())
                section.set_field('cs', sections[section_id].get_flash().get_cs())
                section.set_field('flash_type', sections[section_id].get_flash().get_type())
                section.set_field('size', sections[section_id].get_size())
                # Overcommit is arbitrary for now
                section.set_field('max_size', sections[section_id].get_size())
                byte_field += section.append_fields()
            else:
                section.set_field('uuid', 0x0)
                section.set_field('type', 0x0)
                section.set_field('subtype', 0x0)
                section.set_field('offset', 0x0)
                section.set_field('size', 0x0)
                section.set_field('itf', 0x0)
                section.set_field('cs', 0x0)
                section.set_field('type', 0x0)
                # Overcommit is arbitrary for now
                section.set_field('max_size', 0x0)
        crc = compute_crc(0xFFFFFFFF , byte_field)
        self.header.set_field('crc_table', crc)
        self.header.set_field('crc_header', self.header.get_crc())

    def is_empty(self):

        # Partition table is considered empty in auto mode if all the partitions are considered
        # empty.
        for section in self.sections:
            if not section.is_empty():
                return False

        return True
