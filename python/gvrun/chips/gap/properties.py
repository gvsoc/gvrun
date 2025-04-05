"""
Handles properties for all gap chips.
"""

#
# Copyright (C) 2022 GreenWaves Technologies
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
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

import gvrun.target

def declare_properties(target :gvrun.target.Target, path: str=None):
    """Declare gap properties.

    Parameters
    ----------
    target : gvrun.target.Target
        The target where to add the properties
    """

    # Declare all the properties common to all GAP chips.
    # They must be declared condionnally to not have too many of them.
    target.declare_target_property(
        gvrun.target.Property(
            name='boot.mode', value='flash', path=path,
            description='Specify the way to boot the target',
            allowed_values=['flash', 'jtag', 'spislave']
        )
    )

    target.declare_target_property(
        gvrun.target.Property(
            name='boot.mode_on_pads', value='none', path=path,
            description='Specify the bootmode on the bootsel pads. If it is none, no mode is'
                ' applied',
            allowed_values=['none', 'jtag', 'mram', 'external_flash']
        )
    )

    if target.get_target_property('boot.mode', path=path) == 'flash':

        target.declare_target_property(
            gvrun.target.Property(
                name='boot.flash_device', value='mram', path=path,
                description='In case of flash boot, specify the flash device '
                    'where to boot from',
                allowed_values=['external', 'mram']
            )
        )

    target.declare_target_property(
        gvrun.target.Property(
            name='rom.efuse.usecase.enabled', value='true', path=path,
            description='Enable efuse generation for ROM based on usecases',
            allowed_values=['true', 'false']
        )
    )

    target.declare_target_property(
        gvrun.target.Property(
            name='rom.efuse.usecase.boot_itf', value='0', path=path,
            description='Chip interface that the ROM must use for booting '
                '(for flash and spislave boot)'
        )
    )

    target.declare_target_property(
        gvrun.target.Property(
            name='rom.efuse.usecase.has_slow_ref_clock', value='false', path=path,
            description='Enable slow ref clock',
            allowed_values=['true', 'false']
        )
    )

    target.declare_target_property(
        gvrun.target.Property(
            name='rom.efuse.skip_bootpads', value='true', path=path,
            description='Make the ROM skip the check of the bootpads',
            allowed_values=['true', 'false']
        )
    )
