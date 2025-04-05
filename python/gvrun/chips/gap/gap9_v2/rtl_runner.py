"""
Helper for running RTL simulations on gap9_v2
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

import os
from gapylib.chips.gap.gap9_v2.efuse import EfuseGen
import gapylib.chips.gap.rtl_runner
import gapylib.target
from elftools.elf.elffile import ELFFile


class Runner(gapylib.chips.gap.rtl_runner.Runner):
    """
    Helper class for running execution on gap9_v2 RTL platform.
    """


    def parse_args(self, args: any, gvsoc_cosim=None, gvsoc_config_path=None, full_config=None):

        # If GAP10_HOME is defined, configure automatically the platform from it, otherwise
        # the user have to specify by hands the pathes
        if args.rtl_platform_path is None:
            gap9_home = os.environ.get('GAP9_HOME')
            if gap9_home is not None:

                if args.rtl_simulator == 'vsim':
                    args.rtl_platform_path = os.path.join(gap9_home, 'sim/vsim')
                else:
                    args.rtl_platform_path = os.path.join(gap9_home, 'sim/xcsim')

                args.rtl_platform_sim_path = os.path.join(gap9_home, 'sim')
                os.environ['SIM_PATH'] = args.rtl_platform_sim_path


        super().parse_args(args, gvsoc_cosim=gvsoc_cosim, gvsoc_config_path=gvsoc_config_path,
            full_config=full_config)

        if args.rtl_simulator == 'xcelium':
            self.__set_arg(f'-loadrun {args.rtl_platform_path}/xcelium.d/run.d/librunpost.so')
        self.__set_arg('+VIP_MODE=CUSTOM')
        self.__set_arg('+ENABLE_HYPER0_CS1_PSRAM_VIP=1')
        self.__set_arg('+ENABLE_HYPER0_CS0_MX25U51245G_VIP=1')

        # JTAG boot is using RTL testbench to load the binary as a preload file for the memory
        # through JTAG
        if self.target.get_target_property('boot.mode') == 'jtag':
            # We need to tell the testbench to do so and to give him the binary entry
            with open(self.target.get_args().binary, 'rb') as file:
                entry = ELFFile(file)['e_entry']
                self.__set_arg('+VSIM_BOOTMODE_CFG=1')
                self.__set_arg('+EXEC_TEST=ROM_JTAG_BOOT')
                self.__set_arg('+EXEC_TEST_BOOT_ADDRESS=%x' % entry)


    def image(self):
        super().image()

        # Then the preloading file for the efuses
        self.__gen_efuse_stim()


    def __gen_efuse_stim(self):
        efuse_gen = EfuseGen(self.target)
        efuse_gen.gen_efuse_map()
        efuse_gen.gen_stim(self.target.get_abspath('efuse_preload.data'))
