"""Provides section template for volume table partition second version"""

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
# Antoine Faravelon, GreenWaves Technologies (antoine.faravelon@greenwaves-technologies.com)
#


import dataclasses
from gapylib.flash import FlashSection
from gapylib.utils import CStruct, CStructParent, compute_crc


@dataclasses.dataclass
class VolumeTable(CStruct):
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
        self.add_field('magic_number', 'H')
        # Current number of volumes
        self.add_field('nb_volumes', 'B')
        # Max size of the payload
        self.add_field('max_size', 'I')
        # CRC of the payload
        self.add_field('crc_vtable', 'I')
        # crc of this header
        self.add_field('crc_header', 'I')

    def get_crc(self) -> int:
        """ Get this section's crc

        Returns
        -------
        int
            Section's crc
        """
        byte = bytes(0)

        byte += self.get_field('magic_number').get_bytes()
        byte += self.get_field('nb_volumes').get_bytes()
        byte += self.get_field('max_size').get_bytes()
        byte += self.get_field('crc_vtable').get_bytes()
        crc = 0xFFFFFFFF
        crc = compute_crc(crc,byte)
        return crc

@dataclasses.dataclass
class VolumeHeader(CStruct):
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

        # config flags
        self.add_field('flags', 'H')
        # uuid for this volume
        self.add_field('uuid', 'H')
        # label for this volume
        self.add_field_array('label', 16)
        # Max size of the payload
        self.add_field('nb_partitions', 'B')
        # Max number of partitions in this volume - for dynamic expand
        self.add_field('max_nb_partitions', 'B')
        self.add_field('boot_order', 'B')
        self.add_field('boot_count', 'B')

    def append_fields(self) -> bytes:
        """ Pack this section's fields in a bytes object

        Returns
        -------
        bytes
            Packed bytefield of the payload
        """

        return self.pack()

@dataclasses.dataclass
class VolumeEntry(CStruct):
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
        self.add_field('flags', 'H')
        # Max size of the payload
        self.add_field('uuid', 'H')
        # CRC of the payload
        self.add_field_array('label', 16)

    def append_fields(self) -> bytes:
        """ Pack this section's fields in a bytes object

        Returns
        -------
        bytes
            Packed bytefield of the payload
        """
        return self.pack()

class VolumeTableSection(FlashSection):
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

    def get_payload_byte_field(self) -> bytes:
        """ Pack this section's fields in a bytes object

        Returns
        -------
        bytes
            Packed bytefield of the payload
        """
        byte = bytes(0)
        if self.get_property('volumes') is None:
            byte += self.volume_app.append_fields()
            nb_section = 0
            for _, volume in enumerate(self.volume_app_entries):
                byte += volume.append_fields()
                nb_section+=1
            byte += self.volume_factory.append_fields()
            for _, volume in enumerate(self.volume_factory_entries):
                byte += volume.append_fields()
                nb_section+=1
        else:
            volumes = self.volumes_list
            for volume_id, volume in enumerate(volumes):
                volume_entries_list = self.volume_entries_lists[volume_id]
                byte += volume.append_fields()
                for _, entry in enumerate(volume_entries_list):
                    byte += entry.append_fields()
        return byte

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
        return 0xe1


    def __init__(self, parent, name: str, section_id: int):
        super().__init__(parent, name, section_id)

        self.top_struct = None
        self.header = None
        self.volume_app = None
        self.volume_app_entries = []
        self.volume_factory = None
        self.volume_factory_entries = []
        self.volumes_list = []
        self.volume_entries_lists = []

        self.declare_property(name='volumes', value=None,
            description="Description of voumes (List)."
        )

    def volumes_default_init(self):
        """Set the content of the section in case no specific layout
        was given.

        """
        # Get all the sections to include them in the table
        sections = self.get_flash().get_sections()
        self.volume_app = VolumeHeader('app',parent=self.top_struct)
        section_nb = 0
        for section_id, section in enumerate(sections):
            if section.get_partition_type() != 0x02:
                volume_entry = VolumeEntry(section.get_name(), parent=self.top_struct)
                volume_entry.set_field('uuid',section_id)
                volume_entry.set_field('label',section.get_name().encode('utf-8') + bytes([0]))
                volume_entry.set_field('flags',0x0)
                self.volume_app_entries.append(volume_entry)
                section_nb = section_nb + 1
        self.volume_app.set_field('uuid', 0x0)
        # this is an app volume --> bootable
        self.volume_app.set_field('flags', 0x1)
        self.volume_app.set_field('label', 'app'.encode('utf-8') + bytes([0]))
        self.volume_app.set_field('nb_partitions', section_nb)
        self.volume_app.set_field('max_nb_partitions', section_nb+4)
        for _ in range (4):
            volume_entry = VolumeEntry('none', parent=self.top_struct)
            volume_entry.set_field('uuid',0)
            volume_entry.set_field('label', bytes(16))
            volume_entry.set_field('flags',0x0)
            self.volume_app_entries.append(volume_entry)

        section_nb = 0
        self.volume_factory = VolumeHeader('factory',parent=self.top_struct)
        for section_id, section in enumerate(sections):
            if section.get_partition_type() == 0x02:
                volume_entry = VolumeEntry(section.get_name(), parent=self.top_struct)
                volume_entry.set_field('uuid',section_id)
                volume_entry.set_field('label',section.get_name().encode('utf-8') + bytes([0]))
                volume_entry.set_field('flags',0x0)
                self.volume_factory_entries.append(volume_entry)
                section_nb = section_nb + 1
        self.volume_factory.set_field('uuid', 0x1)
        self.volume_factory.set_field('label', 'factory'.encode('utf-8') + bytes([0]))
        self.volume_factory.set_field('nb_partitions', section_nb)
        self.volume_factory.set_field('max_nb_partitions', section_nb+4)
        for _ in range (4):
            volume_entry = VolumeEntry('none', parent=self.top_struct)
            volume_entry.set_field('uuid',0)
            volume_entry.set_field('label', bytes(16))
            volume_entry.set_field('flags',0x0)
            self.volume_factory_entries.append(volume_entry)

        self.volumes_list.append(self.volume_app)
        self.volumes_list.append(self.volume_factory)


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

        # Main header for readfs size and number of files
        self.header = VolumeTable('header', parent=self.top_struct)

        if self.get_property('volumes') is None:
            self.volumes_default_init()
        else:
            volumes_descr = self.get_property("volumes")
            for volume_id, volume_descr in enumerate(volumes_descr):
                volume_entries_list = []
                volume = VolumeHeader(volume_descr.get('name'), parent=self.top_struct)
                name = volume_descr.get('name')
                volume.set_field('uuid', volume_id)
                volume.set_field('label',name.encode('utf-8') + bytes([0]))
                bootable = volume_descr.get('bootable')
                if bootable is None or bootable is False:
                    volume.set_field('flags', 0x0)
                else:
                    volume.set_field('flags', 0x1)
                boot_order = volume_descr.get('boot_order')
                if boot_order is not None and bootable is True:
                    volume.set_field('boot_order', boot_order)
                entry_nb = 0
                for _, entry_name in enumerate(volume_descr.get('partitions')):
                    entry = VolumeEntry(entry_name, parent=self.top_struct)
                    entry.set_field('label',entry_name.encode('utf-8') + bytes([0]))
                    entry.set_field('flags',0x0)
                    section = self.get_flash().get_target().get_section_by_name(entry_name)
                    uuid = section.get_flash().get_target().get_section_index(entry_name)
                    if uuid is not None:
                        entry.set_field('uuid', uuid)
                    volume_entries_list.append(entry)
                    entry_nb += 1

                entry_nb_max = entry_nb
                if volume_descr.get('free_entry_nb') is not None:
                    for i  in range(volume_descr.get('free_entry_nb')):
                        entry_name = f'free_entry{i}'
                        entry = VolumeEntry(entry_name, parent=self.top_struct)
                        entry.set_field('label',entry_name.encode('utf-8') + bytes([0]))
                        entry.set_field('flags',0x0)
                        volume_entries_list.append(entry)
                    entry_nb_max += volume_descr.get('free_entry_nb')

                volume.set_field('nb_partitions', entry_nb)
                volume.set_field('max_nb_partitions', entry_nb_max)
                self.volumes_list.append(volume)
                self.volume_entries_lists.append(volume_entries_list)

    def finalize(self):
        """Finalize the section.

        This can be called to set internal section fields which requires some knowledge of the
        offset or size of other sections.
        The structure of the section should not be changed in this step
        """
        super().finalize()

        payload_bytes = self.get_payload_byte_field()
        crc = 0xFFFFFFFF
        crc = compute_crc(crc, payload_bytes)
        self.header.set_field('crc_vtable',crc)
        self.header.set_field('max_size',len(payload_bytes))
        self.header.set_field('magic_number',0x01BA)
        self.header.set_field('nb_volumes',len(self.volumes_list))
        self.header.set_field('crc_header',self.header.get_crc())

    def is_empty(self):

        # Partition table is considered empty in auto mode if all the partitions are considered
        # empty.
        return False
