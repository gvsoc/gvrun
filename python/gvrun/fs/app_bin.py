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
# Antoine Faravelon, GreenWaves Technologies (antoine.faravelon@greenwaves-technologies.com)
#


import typing
import dataclasses
import lz4.block
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
    def __init__(self, base: int, compressed: bool, is_overlay: int, section_name: bytes,
                 data: bytes):
        self.base = base
        self.is_overlay = is_overlay
        self.section_name = section_name
        self.data = data
        self.crc = self._compute_crc(self.data)
        #print(f"CRC is: {hex(self.crc)}")
        self.size = len(data)
        self.real_size = len(data)
        self.compressed_data =  bytearray()
        self.compressed = 0
        self.nb_blocks = 0
        #print(f"Full decompressed size is: {hex(self.size)}")
        if compressed is True:
            self.compressed = 1
            # Split the byte into blocks
            while len(data) > (64*1024):
                self.nb_blocks += 1
                chunk = data[:(64*1024)]
                compressed_chunk= lz4.block.compress\
                                            (chunk, mode='high_compression',\
                                            compression=12, return_bytearray=True,\
                                            store_size=False)
                len_raw = len(chunk)-1
                len_compressed = len(compressed_chunk)-1
                if len_compressed < len_raw: # data has been successfuly compressed
                    self.compressed_data.extend(len_raw.to_bytes(2,byteorder='little'))
                    self.compressed_data.extend(len_compressed.to_bytes(2,byteorder='little'))
                    self.compressed_data.extend(compressed_chunk)
                else: # we did not manage to compress, just output the raw block
                    self.compressed_data.extend(len_raw.to_bytes(2,byteorder='little'))
                    self.compressed_data.extend(len_raw.to_bytes(2,byteorder='little'))
                    self.compressed_data.extend(chunk)
                data = data[(64*1024):]
            if len(data) > 0:
                self.nb_blocks += 1
                compressed_chunk= lz4.block.compress\
                                            (data, mode='high_compression',\
                                            compression=12, return_bytearray=True,\
                                            store_size=False)
                len_raw = len(data)-1
                len_compressed = len(compressed_chunk)-1
                if len_compressed < len_raw: # data has been successfuly compressed
                    self.compressed_data.extend(len_raw.to_bytes(2,byteorder='little'))
                    self.compressed_data.extend(len_compressed.to_bytes(2,byteorder='little'))
                    self.compressed_data.extend(compressed_chunk)
                else: # we did not manage to compress, just output the raw block
                    self.compressed_data.extend(len_raw.to_bytes(2,byteorder='little'))
                    self.compressed_data.extend(len_raw.to_bytes(2,byteorder='little'))
                    self.compressed_data.extend(data)
            self.data = self.compressed_data
            self.compressed = 1
        self.real_size = len(self.data)

    def _compute_crc(self, input_data):
        """
        Compute the CRC32 for an ELF segment.
        """
        crc = 0xffffffff
        for data in input_data:
            crc = crc ^ data
            for _ in range(7, -1, -1):
                if crc & 1 == 1:
                    mask = 0xffffffff
                else:
                    mask = 0
                crc = (crc >> 1) ^ (0xEDB88320 & mask)

        return crc ^ 0xffffffff

    def _compute_crc_init(self, input_data, init):
        """
        Compute the CRC32 for an ELF segment.
        """
        crc = init
        for data in input_data:
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

    def __init__(self, file_desc: typing.BinaryIO, compressed: bool):

        # Go through the ELF binary to find the entry point and the segments
        self.segments = []

        elffile = ELFFile(file_desc)
        self.entry = elffile['e_entry']

        for segment in elffile.iter_segments():
            if segment['p_type'] == 'PT_LOAD':
                for section in elffile.iter_sections():
                    if segment.section_in_segment(section):
                        load_addr = 0
                        is_overlay = 0
                        if segment['p_paddr'] < 0xC0000000:
                            load_addr = segment['p_paddr'] +\
                                    (section['sh_addr'] - segment['p_vaddr'])
                        else:
                            load_addr = section['sh_addr']
                            is_overlay = 1
                        # Remove non loadable sections
                        if section['sh_type'] != "SHT_NOBITS" and len(section.data()) > 0:
                            self.segments.append(BinarySegment(load_addr, compressed,\
                                is_overlay, section.name, section.data()))

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
        self.add_field('magic_number', 'I')
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
class AppSectionHeader(CStruct):
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
        # Using the old CRC field to instead detect if this is an overlay
        self.add_field('crc', 'I')
        self.add_field('flags', 'I')
        self.add_field_array('name', 32)



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

    def __init__(self, flash: Flash):
        self.xip_page_size_cmd = 0  # Page size: 0=512B, 1=1KiB, 2=2KiB, ..., 7 = 64KiB
        self.xip_page_size = 512 << self.xip_page_size_cmd
        self.xip_flash_base = None
        self.xip_flash_size = 0
        self.xip_vaddr = 0x20000000
        self.xip_l2_addr = 0x1c190000 - 16*self.xip_page_size
        self.xip_l2_nb_pages = 16
        flash_type = flash.get_flash_attribute('flash_type')
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


class AppBinarySection(FlashSection):
    """
    Class for generating a App Binary section.

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

        self.declare_property(name='compressed', value=False,
            description="Compress the binary."
        )

        self.declare_property(name='subtype', value=None,
            description="Compress the binary."
        )

        self.declare_property(name='binary', value=None,
            description="Executable to be loaded by the ROM."
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
        # This is an app partition
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
        # Subtype is ssbl-loadable app bin, as opposed to rom loadable
        subtype = self.get_property('subtype')
        if subtype is not None:
            if subtype == 'ssbl':
                return 0x72
        return 0x71


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

        if self.binary is None:
            return

        # Then declare the sub-sections so that the right offsets are computed

        # Top structure which will gather all sub-sections
        self.top_struct = CStructParent('rom', parent=self)

        xip = Xip(self.parent)

        xip_segments = []
        static_segments = []

        # Main header
        self.header = RomHeader('Binary header', parent=self.top_struct)

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
            segment = AppSectionHeader('Binary section header', parent=self.top_struct)
            self.segment_headers.append(segment)

        # Apply the XIP alignment to start on XIP page
        if len(xip_segments) > 0:
            padding = CStruct('XIP padding', parent=self.top_struct)
            padding.add_padding('xip padding', align=xip.get_page_size())
            self.align_offset(xip.get_page_size())

        # One header per binary segment
        for binary_segment in binary_segments:
            segment = RomSegment('Binary segment', binary_segment.real_size, parent=self.top_struct)
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
            segment_header.set_field('flags', binary_segment.is_overlay +\
                    (binary_segment.compressed << 1) + (binary_segment.nb_blocks << 24))
            segment_header.set_field('name', binary_segment.section_name.encode('utf-8')\
                    + bytes([0]))

            # Per segment content
            segment.set_field('data', binary_segment.data)


    def finalize(self):
        # If there is no section after the ROM, just take the size as next section offset
        if self.binary is not None:
            self.header.set_field('magic_number', 0xC001B001)


    def __parse_binary(self):
        binary_path = self.get_property('binary')
        compressed = self.get_property('compressed')

        if binary_path is not None:
            try:
                with open(binary_path, "rb") as file_desc:
                    binary = Binary(file_desc, compressed)
            except OSError as esc:
                raise RuntimeError('Invalid rom binary, got error while opening content file: ' + \
                    str(esc)) from esc

        else:
            binary = None

        return binary


    def is_empty(self):
        # In auto-mode flash it only if it has a binary and we are booting from this flash
        return self.binary is None
