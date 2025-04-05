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

import gapylib.target

def declare_properties(target :gapylib.target.Target, path: str=None):
    """Declare gap10 properties.

    Parameters
    ----------
    target : gapylib.target.Target
        The target where to add the properties
    """

    # Declare all the properties for gap10 chip.
    # They must be declared condionnally to not have too many of them.

    target.declare_target_property(
        gapylib.target.Property(
            name='rom.pads', value=None, path=path,
            description='Specifies pads configuration'
        )
    )

    target.declare_target_property(
        gapylib.target.Property(
            name='rom.efuse.secure_boot.enabled', value=0, path=path,
            description='Specifies if aes secured boot is enabled or not',
            allowed_values=['0', '1']
        )
    )

    target.declare_target_property(
        gapylib.target.Property(
            name='rom.efuse.secure_boot.key_size', value=1, path=path,
            description='Specifies aes key size for secure boot, 1 is 256 bits, 0 is 128',
            allowed_values=['0', '1']
        )
    )

    target.declare_target_property(
        gapylib.target.Property(
            name='rom.efuse.secure_boot.key_addr', value=0x4CC, path=path,
            description='Specifies aes key address in puf address map'
        )
    )

    target.declare_target_property(
        gapylib.target.Property(
            name='rom.efuse.secure_boot.forced', value=0, path=path,
            description='Specifies whether to force secure boot or not',
            allowed_values=['0', '1']
        )
    )

    target.declare_target_property(
        gapylib.target.Property(
            name='rom.security.aes_key', value= None, path=path,
            description='AES key to be used by for encryption 128 or 256 bits'
        )
    )

    target.declare_target_property(
        gapylib.target.Property(
            name='rom.security.aes_iv', value= None, path=path,
            description='AES-CTR iv to be used by for encryption - 64 bits'
        )
    )

    target.declare_target_property(
        gapylib.target.Property(
            name='rom.uart.setup', value= False, path=path,
            description='Setup ROM uart proxy'
        )
    )

    if target.get_target_property('rom.uart.setup'):
        target.declare_target_property(
            gapylib.target.Property(
                name='rom.uart.ctrl_flow', value= False, path=path,
                description='Enable control flow for ROM uart proxy'
            )
        )

    if target.get_target_property('rom.uart.setup'):
        target.declare_target_property(
            gapylib.target.Property(
                name='rom.uart.password', value=None, path=path,
                description='Specify expected password to allow uart connection'
            )
        )

    target.declare_target_property(
        gapylib.target.Property(
            name='rom.pad_unlatch', value=None, cast=int, path=path,
            description='When specified, gives the pads to be unlatched after wakeup'
        )
    )
