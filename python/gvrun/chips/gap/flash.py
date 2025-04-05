"""Default flash description for all gap targets"""

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


import json
from collections import OrderedDict
from gapylib.chips.gap.target import Target
from gapylib.flash import Flash
from gapylib.fs.littlefs import LfsSection
from gapylib.fs.readfs import ReadfsSection
from gapylib.fs.writefs import WriteFsSection
from gapylib.fs.hostfs import HostfsSection
from gapylib.fs.raw import RawSection
import gapylib.chips.gap.rom_v2
import gapylib.chips.gap.rom_v3
from gapylib.chips.gap.meta_table import FsblMetaTableSection
from gapylib.fs.partition import PartitionTableSection
from gapylib.fs.partition_v2 import PartitionTableSectionV2
from gapylib.fs.app_bin import AppBinarySection
from gapylib.fs.volume_table import VolumeTableSection
from gapylib.fs.secret_storage import SecretStorageSection


class DefaultFlashRom(Flash):
    """
    Default class for all flash for gap targets.
    Mostly describes the allowed section templates (rom and all FS).

    Attributes
    ----------
    target : gapylib.target.Target
        Target containing the flash.
    name : str
        Name of the flash
    size : int
        Size of the flash
    rom_section
        Rom section
    """

    def __init__(self, target: Target, name: str, size: int, rom_section, *kargs, **kwargs):
        super().__init__(target, name, size, *kargs, **kwargs)

        # Declare all the available flash section
        self.register_section_template('rom', rom_section)
        self.register_section_template('app binary', AppBinarySection)
        self.register_section_template('meta table', FsblMetaTableSection)
        self.register_section_template('partition table', PartitionTableSection)
        self.register_section_template('partition table v2', PartitionTableSectionV2)
        self.register_section_template('volume table', VolumeTableSection)
        self.register_section_template('secret storage', SecretStorageSection)
        self.register_section_template('readfs', ReadfsSection)
        self.register_section_template('writefs', WriteFsSection)
        self.register_section_template('hostfs', HostfsSection)
        self.register_section_template('lfs', LfsSection)
        self.register_section_template('raw', RawSection)

        # And give the default layout
        content_file = 'gapylib/chips/gap/default_flash_content.json'
        content_path = target.get_file_path(content_file)

        if content_path is None:
            raise RuntimeError('Could not find flash property file: ' + content_file)

        try:
            with open(content_path, 'rb') as file_desc:
                self.set_content(json.load(file_desc, object_pairs_hook=OrderedDict))
        except OSError as exc:
            raise RuntimeError('Unable to open flash content file: ' + str(exc)) from exc

    def get_type(self) -> int:
        """Get flash type
        Returns
        -------
        int
            integer value of type, with respect to fpv2
        """
        flash_type = self.flash_attributes.get('flash_type')
        if flash_type is not None:
            if flash_type == 'mram':
                return 0x0
            if flash_type == 'spi':
                return 0x1
            if flash_type == 'hyper':
                return 0x2
        return 0xff

    def get_itf(self) -> int:
        """Get flash itf
        Returns
        -------
        int
            integer value of itf, with respect to gap9
        """
        if self.flash_attributes.get('itf') is not None:
            return self.flash_attributes.get('itf')
        return 0x0

    def get_cs(self) -> int:
        """Get flash cs
        Returns
        -------
        int
            integer value of cs, with respect to gap9
        """
        if self.flash_attributes.get('cs') is not None:
            return self.flash_attributes.get('cs')
        return 0x0


class DefaultFlashRomV2(DefaultFlashRom):
    """
    Default class for all flash for gap targets.
    Mostly describes the allowed section templates (rom and all FS).

    Attributes
    ----------
    target : gapylib.target.Target
        Target containing the flash.
    name : str
        Name of the flash
    size : int
        Size of the flash
    """

    def __init__(self, target: Target, name: str, size: int, *kargs, **kwargs):
        super().__init__(target, name, size, gapylib.chips.gap.rom_v2.RomFlashSection, *kargs,
            **kwargs)


class DefaultFlashRomV3(DefaultFlashRom):
    """
    Default class for all flash for gap targets.
    Mostly describes the allowed section templates (rom and all FS).

    Attributes
    ----------
    target : gapylib.target.Target
        Target containing the flash.
    name : str
        Name of the flash
    size : int
        Size of the flash
    """

    def __init__(self, target: Target, name: str, size: int, *kargs, **kwargs):
        super().__init__(target, name, size, gapylib.chips.gap.rom_v3.RomFlashSection, *kargs,
            **kwargs)
