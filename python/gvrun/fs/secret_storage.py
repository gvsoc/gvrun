"""Provides section template for secure storage"""

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

# Authors:
# Antoine Faravelon, GreenWaves Technologies (antoine.faravelon@greenwaves-technologies.com)
#


import dataclasses
import math
from gapylib.flash import FlashSection
from gapylib.utils import CStruct, CStructParent, compute_crc


@dataclasses.dataclass
class SecretStorageSecureHeader(CStruct):
    """
    Class for secure header (first bytes, used to decrypt the rest).

    Attributes
    ----------
    name : str
        Name of this sub-section.

    parent : str
        Parent, which is aggregating all readfs sub-sections.
    """
    def __init__(self, name: str, parent: CStructParent):
        super().__init__(name, parent)

        # Ignored if fused --> else, if 0, init an AC and get ready to receive keys
        self.add_field('valid', 'B')
        # AC used to encrypt this partition's metadata  (ID 0 by convention)
        self.add_field_array('ac',996)
        self.add_field_array('padding0', 11)
        self.add_field('crc', 'I')
        self.add_field_array('padding1', 12)

@dataclasses.dataclass
class SecretStorageMetaHeader(CStruct):
    """
    Metadata part of the secret storage header (encrypted).

    Attributes
    ----------
    name : str
        Name of this sub-section.

    parent : str
        Parent, which is aggregating all readfs sub-sections.
    """
    def __init__(self, name: str, nb_kc: int, parent: CStructParent):
        super().__init__(name, parent)

        # Number of ACs and KCs, AC size is fixed, so we start with them
        # Padded to ease encryption
        # CRC of the section
        self.add_field('kc_number', 'B')
        nb_key = 0
        for kc_id in range(0,nb_kc):
            self.add_field('offset' + str(kc_id), 'I')
            nb_key += 1
        self.add_field_array('padding0', 16-(((nb_key*4) +1)%16))

    def set_kc_offsets(self, offsets: [int]):
        """ set offsets of each KC subsections, since size isn't fixed.
        Parameters
        ----------
        offsets: [int]
            List of offsets (int)
        """
        for kc_id, kc_offset in enumerate(offsets):
            self.set_field('offset' + str(kc_id), kc_offset)

@dataclasses.dataclass
class SecretStorageKC(CStruct):
    """
    Secret storage key code.

    Attributes
    ----------
    name : str
        Name of this sub-section.
    source_size : str
        Size of the source key.

    parent : str
        Parent, which is aggregating all readfs sub-sections.
    """
    def __init__(self, name: str, source_size: int, flags: int, parent: CStructParent):
        super().__init__(name, parent)
        if flags is True:
            kc_size = self.kc_size_compute(source_size)
        else:
            # Just align the size u
            kc_size = source_size//8
            if (kc_size % 16) != 0:
                kc_size += (16 - (kc_size%16))
        # Magic number
        self.add_field('kc_size', 'H')
        self.add_field('kc_so_id', 'B')
        self.set_field('kc_size', kc_size)
        self.add_field('flags', 'B')
        if flags is True:
            self.set_field('flags', 1)
        else:
            self.set_field('flags', 0)
        # Need to have a natural alignment to avoid issues when writing
        # Max size of the payload
        self.add_field_array('kc', kc_size)
        # Pad to 16 byte boundary
        self.add_field_array('padding1',
                             16-((kc_size+4)% 16))

    def append_fields(self) -> bytes:
        """ Pack this section's fields in a bytes object

        Returns
        -------
        bytes
            Packed bytefield of the payload
        """
        return self.pack()

    def kc_size_compute(self, source_size: int) -> int:
        """ Compute KC size from source size

        Parameters
        ----------
        source_size: int
            Input size
        Returns
        -------
        int
            Resulting KC's size
        """
        kc_size = 36 + math.floor(source_size / 8) + (16 * math.ceil(source_size/384))
        return kc_size

    def get_real_size(self) -> int:
        """ Compute KC size from source size

        Parameters
        ---------
        source_size: int
            Input size
        Returns
        -------
        int
            Resulting KC's size
        """
        return len(self.pack())

class SecretStorageSection(FlashSection):
    """
    Class for generating a volume table section.

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

        self.top_struct = None
        self.header_secure = None
        self.header_meta = None
        self.ac_list = []
        self.kc_list = []
        self.ac_number = None
        self.kc_number = None

        self.declare_property(name='ac_list', value=None,
            description="Description of Activation codes."
        )

        self.declare_property(name='kc_list', value=None,
            description="Description of key codes."
        )

        self.declare_property(name='encrypted', value=None,
            description="Should the section itself be encrypted."
        )

    def get_payload_crc(self) -> int:
        """ Pack this section's fields in a bytes object

        Returns
        -------
        bytes
            Packed bytefield of the payload
        """
        byte = bytes(0)
        byte += self.header_meta.pack()
        for _, ac_section in enumerate(self.ac_list):
            byte += ac_section.pack()
        for _, kc_section in enumerate(self.kc_list):
            byte += kc_section.pack()
        crc = compute_crc(0xFFFFFFFF, byte)
        return crc

    def get_partition_type(self)-> int:
        """Return the partition type.

        This information can be used by the partition table as the type.

        Returns
        -------
        int
            The partition type.
        """
        return 0x2

    def get_partition_subtype(self)-> int:
        """Return the partition subtype.

        This information can be used by the partition table as the subtype.

        Returns
        -------
        int
            The partition type.
        """
        return 0xe5


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

        # First declare the sub-sections so that the right offsets are computed

        # Top structure which will gather all sub-sections
        self.top_struct = CStructParent('partition table v2',parent=self)

        kc_list_descr = self.get_property("kc_list")
        # Main header for readfs size and number of files
        self.header_secure = SecretStorageSecureHeader('SecureHeader',
                                                       parent=self.top_struct)
        self.header_meta = SecretStorageMetaHeader('MetaHeader', len(kc_list_descr),
                                                       parent=self.top_struct)

        self.kc_number = 0
        kc_offset = 0
        kc_offsets = []
        for _, kc_descr in enumerate(kc_list_descr):
            wrapped = kc_descr.get('wrapped')
            kc_size = kc_descr.get('size')
            if wrapped is not None and wrapped is True:
                if (kc_size  > 1023 and (kc_size % 1024) != 0) or \
                (kc_size <1024 and (kc_size % 64) !=0):
                    raise RuntimeError(f'size {kc_size} is to big for wrapping, max is 4096')
            if wrapped is None:
                if kc_size > 1023:
                    wrapped = False
                else:
                    wrapped = True
            kc_section = SecretStorageKC(kc_descr.get('name'), kc_descr.get('size')
                                         ,wrapped
                                         ,parent=self.top_struct)
            self.kc_list.append(kc_section)
            self.kc_number += 1
            kc_offsets.append(kc_offset)
            kc_offset += kc_section.get_real_size()

        self.header_meta.set_kc_offsets(kc_offsets)

        self.header_meta.set_field('kc_number', self.kc_number)
        encrypted = self.get_property('encrypted')
        if encrypted is not None and encrypted is True:
            self.header_secure.set_field('valid', 0x01<<1)

    def finalize(self):
        """Finalize the section.

        This can be called to set internal section fields which requires some knowledge of the
        offset or size of other sections.
        The structure of the section should not be changed in this step
        """
        super().finalize()

        self.header_secure.set_field('crc', self.get_payload_crc())

    def is_empty(self):

        # Partition table is considered empty in auto mode if all the partitions are considered
        # empty.
        return False
