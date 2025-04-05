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


import typing
import dataclasses
from elftools.elf.elffile import ELFFile
from gapylib.flash import FlashSection, Flash
from gapylib.utils import CStruct, CStructParent



@dataclasses.dataclass
class BinarySegment():
    """
    Class for describing an ELF segment.

    Attributes
    ----------
    base : int
        Name of this sub-section.

    data : bytes
        Content of the section
    """
    def __init__(self, base: int, data: bytes):
        self.base = base
        self.data = data
        self.size = len(data)
        self.crc = self._compute_crc()

    def _compute_crc(self):
        """
        Compute the CRC32 for an ELF segment.
        """
        crc = 0xffffffff
        for data in self.data:
            crc = crc ^ data
            for _ in range(7, -1, -1):
                if crc & 1 == 1:
                    mask = 0xffffffff
                else:
                    mask = 0
                crc = (crc >> 1) ^ (0xEDB88320 & mask)

        return crc ^ 0xffffffff




@dataclasses.dataclass
class Binary():
    """
    Class for describing an ELF binary.

    Attributes
    ----------
    fd
        File descriptor
    """

    def __init__(self, file_desc: typing.BinaryIO):

        # Go through the ELF binary to find the entry point and the segments
        self.segments = []

        elffile = ELFFile(file_desc)
        self.entry = elffile['e_entry']

        for segment in elffile.iter_segments():
            if segment['p_type'] == 'PT_LOAD':
                self.segments.append(BinarySegment(segment['p_paddr'], segment.data()))



@dataclasses.dataclass
class RomEmptyHeader(CStruct):
    """
    Class for generating rom sub-section containing the main header when the ROM section is empty
    (when there is no binary)

    Attributes
    ----------
    name : str
        Name of this sub-section.

    parent : str
        Parent, which is aggregating all rom sub-sections.
    """

    def __init__(self, name, parent):
        super().__init__(name, parent)

        # Size of the whole rom section, used by the runtime to find the next section.
        self.rom_header_size    = self.add_field('next_section', 'I')



@dataclasses.dataclass
class RomHeader(CStruct):
    """
    Class for generating rom sub-section containing the main header when the ROM section is not
    empty (when there is a binary)

    Attributes
    ----------
    name : str
        Name of this sub-section.

    parent : str
        Parent, which is aggregating all rom sub-sections.
    """

    def __init__(self, name, parent: CStructParent):
        super().__init__(name, parent)

        # Size of the whole rom section, used by the runtime to find the next section.
        self.add_field('next_section', 'I')
        # Number of binary segments to be loaded from flash to chip memory
        self.add_field('nb_segments', 'I')
        # Binary entry point
        self.add_field('entry', 'I')
        # Unused
        self.add_field('unused', 'I')

        # XIP device ID where XIP binary is stored (0: hyper, 1: spi, 2: mram)
        self.add_field('xip_dev', 'I')
        # XIP chip address where the XIP code is accessed
        self.add_field('xip_vaddr', 'I')
        # Size of an XIP page
        self.add_field('xip_page_size', 'I')
        # Offset in the flash where the XIP blocks are stored
        self.add_field('xip_flash_base', 'I')
        # Number of flash pages where which can be fetched by the XIP cache
        self.add_field('xip_flash_nb_pages', 'I')
        # Address in L2 where the XIP cache is
        self.add_field('xip_l2_base', 'I')
        # Number of L2 pages reserved for the XIP cache
        self.add_field('xip_l2_nb_pages', 'I')

        self.add_field('kc_length', 'I')
        self.add_field('key_length', 'I')
        self.add_field_array('ac', 1024)
        self.add_field_array('kc', 128)
        self.add_field_array('kc_write', 128)



@dataclasses.dataclass
class RomSegmentHeader(CStruct):
    """
    Class for generating rom sub-section containing a segment header.

    Attributes
    ----------
    name : str
        Name of this sub-section.

    parent : str
        Parent, which is aggregating all rom sub-sections.
    """

    def __init__(self, name, parent: CStructParent):
        super().__init__(name, parent)

        # Flash offset of the segment content (the offset is relative to the
        # start of the section)
        self.add_field('flash_offset', 'I')
        # Chip memory address where to load the segment
        self.add_field('mem_addr', 'I')
        # Size of the segment
        self.add_field('size', 'I')
        # Unused
        self.add_field('crc', 'I')



@dataclasses.dataclass
class RomSegment(CStruct):
    """
    Class for generating rom sub-section containing a segment.

    Attributes
    ----------
    name : str
        Name of this sub-section.

    parent : str
        Parent, which is aggregating all rom sub-sections.
    """

    def __init__(self, name, size, parent: CStructParent):
        super().__init__(name, parent)

        # Segment content
        self.add_field_array('data', size)


class Xip():
    """
    Class for handling XIP support for ROM

    Attributes
    ----------
    flash : Flash
        Flash where the ROM section is.
    """

    def __init__(self, flash: Flash, page_size_cmd, flash_base, nb_pages, vaddr):
        self.xip_page_size_cmd = page_size_cmd  # Page size: 0=512B, 1=1KiB, 2=2KiB, ..., 7 = 64KiB
        self.xip_page_size = 512 << self.xip_page_size_cmd
        self.xip_flash_base = flash_base # start address in flash
        self.xip_flash_size = 0
        self.xip_vaddr = vaddr
        self.xip_l2_nb_pages = nb_pages
        self.xip_l2_addr = 0x1c190000 - self.xip_l2_nb_pages*self.xip_page_size
        flash_type = flash.get_flash_type()
        if flash_type == 'hyper':
            self.xip_dev = 0
        elif flash_type == 'spi':
            self.xip_dev = 1
        elif flash_type == 'mram':
            self.xip_dev = 2
        else:
            raise RuntimeError(
                f'Flash type {flash_type} not suported. ROM boot loader supports hyper, spi'
                    'and mram flash type')


    def is_xip_segment(self, base: int) -> bool:
        """Tell if the segment is an XIP one.

        Returns
        -------
        bool
            True if the segment is an XIP one, False otherwise.
        """
        return base >= self.xip_vaddr


    def fill_header(self, header: RomHeader):
        """Fill XIP information into ROM main header.

        Parameters
        ----------
        header : RomHeader
            Name of the field
        """
        flash_nb_pages = int((self.xip_flash_size + self.xip_page_size-1) / self.xip_page_size)
        header.set_field('xip_dev', self.xip_dev)
        header.set_field('xip_vaddr', self.xip_vaddr)
        header.set_field('xip_page_size', self.xip_page_size_cmd)
        header.set_field('xip_flash_base',
            0 if self.xip_flash_base is None else self.xip_flash_base)
        header.set_field('xip_flash_nb_pages', flash_nb_pages)
        header.set_field('xip_l2_base', self.xip_l2_addr)
        header.set_field('xip_l2_nb_pages', self.xip_l2_nb_pages)


    def get_page_size(self) -> int:
        """Get XIP page size.

        Returns
        -------
        int
            Page size.
        """
        return self.xip_page_size


    def register_segment(self, offset: int, size: int):
        """Register XIP segment.

        This is used to compute the size of the XIP area.

        Parameters
        ----------
        offset : int
            Base offset of the segment.
        size: int
            Size of the segment.
        """
        self.xip_flash_size += size
        if self.xip_flash_base is None:
            self.xip_flash_base = offset


class RomFlashSection(FlashSection):
    """
    Class for generating a ROM section.

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

        self.segment_headers = []
        self.segments = []
        self.binary = None
        self.top_struct = None
        self.header = None
        self.boot = False

        self.declare_property(name='binary', value=None,
            description="Executable to be loaded by the ROM."
        )

        self.declare_property(name='boot', value=False,
            description="True if the ROM will boot using this ROM section."
        )

        self.declare_property(name='subtype', value=None,
            description="Subtype of the binary partition, ssbl, fsbl or any."
        )

        self.declare_property(name='xip_virtual_address', value=0x20000000,
            description="Virtual address to be used for XIP."
        )

        self.declare_property(name='xip_flash_address', value=None,
            description="Base address in flash to be used for XIP."
        )

        self.declare_property(name='xip_page_size', value=0x0,
            description="Log(Page size) - 9 used by XIP."
        )

        self.declare_property(name='xip_page_number', value=0x10,
            description="Number of pages used by XIP."
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
        subtype = self.get_property('subtype')
        if subtype is not None:
            if subtype == 'ssbl':
                return 0x2
            if subtype == 'fsbl':
                return 0x2
        # otherwise, this is an app partition
        return 0x0

    def get_partition_subtype(self)-> int:
        """Return the partition subtype.

        This information can be used by the partition table as the subtype.
        This method returns an unknown type (0xff) and should be overloaded by real sections.

        Returns
        -------
        int
            The partition type.
        """
        subtype = self.get_property('subtype')
        if subtype is not None:
            if subtype == 'ssbl':
                return 0xe3
            if subtype == 'fsbl':
                return 0xe2
        # otherwise, this is unknown for now
        return 0xff


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
        self.binary = self.__parse_binary()

        self.boot = self.get_property('boot')

        # Then declare the sub-sections so that the right offsets are computed

        # Top structure which will gather all sub-sections
        self.top_struct = CStructParent('rom', parent=self)


        #self.declare_property(name='xip_virtual_address', value=None,
        #    description="Virtual address to be used for XIP."
        #)

        #self.declare_property(name='xip_flash_address', value=None,
        #    description="Base address in flash to be used for XIP."
        #)

        #self.declare_property(name='xip_page_size', value=None,
        #    description="Page size used by XIP."
        #)

        #self.declare_property(name='xip_page_number', value=None,
        #    description="Number of pages used by XIP."
        #)

        # cmd, flash_base, nb_page, vaddr
        xip_page_size_cmd =  int(self.get_property('xip_page_size'))
        if self.get_property('xip_flash_address') is None:
            xip_flash_addr = None
        else:
            xip_flash_addr = int(self.get_property('xip_flash_address'))
        xip_page_nb =  int(self.get_property('xip_page_number'))
        xip_vaddr = self.get_property('xip_virtual_address')
        if isinstance(xip_vaddr,str):
            xip_vaddr = int(xip_vaddr,16)
        xip = Xip(self.parent, xip_page_size_cmd, xip_flash_addr, xip_page_nb, xip_vaddr)

        if self.binary is not None:
            xip_segments = []
            static_segments = []

            # Main header
            self.header = RomHeader('ROM header', parent=self.top_struct)

            # First go through all segments to gather XIP segments together since they need to be
            # contiguous in flash.
            for i, binary_segment in enumerate(self.binary.segments):
                if xip.is_xip_segment(binary_segment.base):
                    xip_segments.append(binary_segment)
                else:
                    static_segments.append(binary_segment)

            # Gether all segments together with first XIP segments
            binary_segments = xip_segments + static_segments

            # One header per binary segment for describing it (size, etc)
            for __ in binary_segments:
                segment = RomSegmentHeader('Binary segment header', parent=self.top_struct)
                self.segment_headers.append(segment)

            # Apply the XIP alignment to start on XIP page
            if len(xip_segments) > 0:
                padding = CStruct('XIP padding', parent=self.top_struct)
                padding.add_padding('xip padding', align=xip.get_page_size())
                self.align_offset(xip.get_page_size())

            # One header per binary segment
            for binary_segment in binary_segments:
                segment = RomSegment('Binary segment', binary_segment.size, parent=self.top_struct)
                self.segments.append(segment)

                # If the segment is an XIP one, take it into account for offset and size
                # computation.
                if xip.is_xip_segment(binary_segment.base):
                    xip.register_segment(segment.get_offset(),binary_segment.size)

            # Now that the offsets have been computed, we can fill-in the various fields

            # Main header
            # Note that the next section offset is set during finalize step since offsets are not
            # known yet
            self.header.set_field('nb_segments', len(self.binary.segments))
            self.header.set_field('entry', self.binary.entry)

            xip.fill_header(self.header)

            for i, binary_segment in enumerate(binary_segments):
                segment_header = self.segment_headers[i]
                segment = self.segments[i]

                # Per-segment header

                # addresses are relative to the start of the section
                # This allows romv2 sections to be move anywhere in memory
                addr_offset = segment.get_field('data').get_offset() - self.get_offset()

                segment_header.set_field('flash_offset', addr_offset)
                segment_header.set_field('mem_addr', binary_segment.base)
                segment_header.set_field('size', binary_segment.size)
                segment_header.set_field('crc', binary_segment.crc)

                # Per segment content
                segment.set_field('data', binary_segment.data)

        else:
            # Case where the ROM is empty. In this case, we just have the ROM section size
            self.header = RomEmptyHeader('ROM header', parent=self.top_struct)


    def finalize(self):
        # If there is no section after the ROM, just take the size as next section offset
        next_section = self.get_next_section()
        if next_section is None:
            next_section_offset = self.get_offset() + self.get_size()
        else:
            next_section_offset = next_section.get_offset()

        self.header.set_field('next_section', next_section_offset)


    def __parse_binary(self):
        binary_path = self.get_property('binary')

        if binary_path is not None:
            try:
                with open(binary_path, "rb") as file_desc:
                    binary = Binary(file_desc)
            except OSError as esc:
                raise RuntimeError('Invalid rom binary, got error while opening content file: ' + \
                    str(esc)) from esc

        else:
            binary = None

        return binary


    def is_empty(self):
        # In auto-mode flash it only if it has a binary and we are booting from this flash
        return self.binary is None or not self.boot
