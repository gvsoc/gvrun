"""Provides section template for gap rom v2 (starting from gap9_v2)"""

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
#


import dataclasses
from gapylib.flash import FlashSection, Flash
from gapylib.utils import CStruct, CStructParent

@dataclasses.dataclass
class SsblHeader(CStruct):
    """
    Class for generating meta table SSBL subsection only necessary if using
    redundancy w/ FSBL + SSBL schema

    Attributes
    ----------
    name : str
        Name of this sub-section.

    parent : str
        Parent, which is aggregating SSBL and Partition table redundancy entries.
    """

    def __init__(self, name, parent: CStructParent):
        super().__init__(name, parent)

        # Only the lower bit is actually significant, but we use a whole row
        # for atomicity --> Hypothesis is that we are using eMRAM
        self.add_field_array('ssbl_a_not_b', 16)

        ## SSBL A section
        # CRC for SSBL A addr
        self.add_field('ssbl_a_crc', 'I')
        # SSBL A entry point
        self.add_field('ssbl_a_addr', 'I')
        # Unused
        self.add_field_array('pad_ssbl_a', 8)

        ## SSBL B section
        # CRC for SSBL B addr
        self.add_field('ssbl_b_crc', 'I')
        # SSBL A entry point
        self.add_field('ssbl_b_addr', 'I')
        # Unused
        self.add_field_array('pad_ssbl_b', 8)

@dataclasses.dataclass
class PartitionTableHeader(CStruct):
    """
    Class for generating meta table Partition Table subsection.
    Useful to recover from partition table corruption.

    Attributes
    ----------
    name : str
        Name of this sub-section.

    parent : str
        Parent, which is aggregating all rom sub-sections.
    """

    def __init__(self, name, parent: CStructParent):
        super().__init__(name, parent)

        ## Partition Table A section
        # CRC for Partition Table A addr
        self.add_field('pt_a_crc', 'I')
        # SSBL A entry point
        self.add_field('pt_a_addr', 'I')
        # Unused
        self.add_field_array('pad_pt_a', 8)

        ## Partition Table B section
        # CRC for Partition Table B addr
        self.add_field('pt_b_crc', 'I')
        # Partition Table A entry point
        self.add_field('pt_b_addr', 'I')
        # Unused
        self.add_field_array('pad_pt_b', 8)

@dataclasses.dataclass
class MetaTableNext(CStruct):
    """
    Class for generating meta table Partition Table subsection.
    Useful to recover from partition table corruption.

    Attributes
    ----------
    name : str
        Name of this sub-section.

    parent : str
        Parent, which is aggregating all rom sub-sections.
    """

    def __init__(self, name, parent: CStructParent):
        super().__init__(name, parent)

        ## Partition Table A section
        # CRC for Partition Table A addr
        self.add_field('next_section', 'I')
        self.add_field_array('pad', 12)

class FsblMetaTableSection(FlashSection):
    """
    Class for generating a Meta Table section.

    Attributes
    ----------
    parent: gapylib.flash.Flash
        Name of the section.
    name : str
        Name of the section.
    section_id : int
        Id of the section.
    """

    def __init__(self, parent: Flash, name: str, section_id: int):
        super().__init__(parent, name, section_id)

        self.meta_table = None
        self.ssbl_header = None
        self.partition_table_header = None
        self.next_section = None

        self.declare_property(name='ssbl_a', value=None,
            description="A copy of the ssbl."
        )
        self.declare_property(name='ssbl_b', value=None,
            description="B copy of the ssbl."
        )
        self.declare_property(name='pt_a', value=None,
            description="A copy of the Parttion table."
        )
        self.declare_property(name='pt_b', value=None,
            description="B copy of the partition table."
        )

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
        return 0xe4



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

        # First parse the ELF binary if any


        # Then declare the sub-sections so that the right offsets are computed

        # Top structure which will gather all sub-sections
        self.meta_table = CStructParent('meta_table', parent=self)
        self.next_section = MetaTableNext("next section", parent=self.meta_table)
        self.ssbl_header = SsblHeader('SSBL header', parent=self.meta_table)
        self.partition_table_header = PartitionTableHeader(
                'Partition Table header', parent=self.meta_table)

    def finalize(self):
        # If there is no section after the ROM, just take the size as next section offset
        which_ssbl = [0, 0, 0, 0] + [0]*12 # SSBL_A
        #which_ssbl = [1, 0, 0, 0] + [0]*12 # SSBL_B
        self.ssbl_header.set_field('ssbl_a_not_b', bytes(which_ssbl))
        self.ssbl_header.set_field('ssbl_a_addr', 0xDEADBEEF)
        self.ssbl_header.set_field('ssbl_b_addr', 0xDEADBEEF)
        self.partition_table_header.set_field('pt_a_addr', 0xDEADBEEF)
        self.partition_table_header.set_field('pt_b_addr', 0xDEADBEEF)

        ssbl_a_name = self.get_property('ssbl_a')
        if ssbl_a_name is not None:
            ssbl_section = self.parent.get_section_by_name(ssbl_a_name)
            if ssbl_section is not None:
                self.ssbl_header.set_field('ssbl_a_addr', ssbl_section.get_offset())
        ssbl_b_name = self.get_property('ssbl_b')
        if ssbl_b_name is not None:
            ssbl_section = self.parent.get_section_by_name(ssbl_b_name)
            if ssbl_section is not None:
                self.ssbl_header.set_field('ssbl_b_addr', ssbl_section.get_offset())
        pt_b_name = self.get_property('pt_b')
        if pt_b_name is not None:
            pt_section = self.parent.get_section_by_name(pt_b_name)
            if pt_section is not None:
                self.partition_table_header.set_field('pt_b_addr', pt_section.get_offset())
        pt_a_name = self.get_property('pt_a')
        if pt_a_name is not None:
            pt_section = self.parent.get_section_by_name(pt_a_name)
            if pt_section is not None:
                self.partition_table_header.set_field('pt_a_addr', pt_section.get_offset())
        if self.get_next_section() is not None:
            self.next_section.set_field('next_section', self.get_next_section().get_offset())
        else:
            self.next_section.set_field('next_section', self.get_offset() + self.get_size())

    def is_empty(self):
        # In auto-mode flash it only if it has a binary and we are booting from this flash
        return False
