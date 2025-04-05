"""
Helper for running RTL simulations on gap10
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

import shutil
import os.path
import filecmp
from gapylib.chips.gap.gap10.efuse import EfuseGen
import gapylib.chips.gap.rtl_runner
import gapylib.target
from elftools.elf.elffile import ELFFile


class Runner(gapylib.chips.gap.rtl_runner.Runner):
    """
    Helper class for running execution on gap10 RTL platform.
    """


    def parse_args(self, args: any, gvsoc_cosim=None, gvsoc_config_path=None, full_config=None):

        # If GAP10_HOME is defined, configure automatically the platform from it, otherwise
        # the user have to specify by hands the pathes
        if args.rtl_platform_path is None:
            gap10_home = os.environ.get('GAP10_HOME')
            if gap10_home is not None:

                if args.rtl_simulator == 'vsim':
                    args.rtl_platform_path = os.path.join(gap10_home, 'sim/vsim')
                else:
                    args.rtl_platform_path = os.path.join(gap10_home, 'sim/xcsim')

                args.rtl_platform_sim_path = os.path.join(gap10_home, 'sim')
                os.environ['SIM_PATH'] = args.rtl_platform_sim_path

        super().parse_args(args, gvsoc_cosim=gvsoc_cosim, gvsoc_config_path=gvsoc_config_path,
            full_config=full_config)

        # Force to mram boot
        # self.__set_arg('+VSIM_BOOTMODE_CFG=3')
        # self.__set_arg('+VIP_MODE=CUSTOM')
        # self.__set_arg('+ENABLE_HYPER0_CS1_PSRAM_VIP=1')
        # self.__set_arg('+ENABLE_HYPER0_CS0_MX25U51245G_VIP=1')
        self.__set_arg('+UVM_VERBOSITY=UVM_LOW')
        self.__set_arg('+UVM_TESTNAME=csi2_rx_pkt_raw8')
        self.__set_arg('+phy_sel=dphy')
        self.__set_arg('+lane=2lane')
        self.__set_arg('+data_width=8bit')
        self.__set_arg('+frame_mode=Gen')

        # Set the right path to otp depending on whether we take the precomputed one or we
        # generate one.
        if self.target.get_target_property('rom.efuse.usecase.enabled') == 'true':
            self.__set_arg(f'+OTP_FILE_PATH={self.target.get_working_dir()}/EGP256X32')

        if self.target.get_target_property('boot.mode_on_pads') == 'jtag':
            self.__set_arg('+VSIM_BOOTMODE_CFG=1')

        # JTAG boot is using RTL testbench to load the binary as a preload file for the memory
        # through JTAG
        if self.target.get_target_property('boot.mode') == 'jtag' or \
                self.target.get_target_property('boot.mode_on_pads') == 'jtag':
            # We need to tell the testbench to do so and to give him the binary entry
            with open(args.binary, 'rb') as file:
                entry = ELFFile(file)['e_entry']
                if self.target.get_target_property('boot.mode_on_pads') == 'jtag':
                    self.__set_arg('+EXEC_TEST=ROM_JTAG_BOOT')
                else:
                    self.__set_arg('+EXEC_TEST=ROM_JTAG_BOOT_FROM_EFUSE')
                self.__set_arg('+EXEC_TEST_BOOT_ADDRESS=%x' % entry)

        if self.target.get_target_property('boot.mode') == 'spislave':
            with open(args.binary, 'rb') as file:
                entry = ELFFile(file)['e_entry']
                full_config.set('target/testbench/testbench/spislave_boot/stim_file',
                    'slm_files/l2_stim.slm')
                full_config.set('target/testbench/testbench/spislave_boot/entry', '0x%x' % entry)




    def image(self):
        super().image()

        # Then the preloading file for the efuses
        self.__gen_efuse_stim()


    def __gen_efuse_stim(self):

        local_efuse = self.target.get_abspath('efuse_preload.data')
        ref_efuse = self.target.get_file_path('gapylib/chips/gap/gap10/efuse_preload.data')

        efuse_gen = EfuseGen(self.target)
        efuse_gen.gen_efuse_map()
        efuse_gen.gen_stim(local_efuse)

        # Since generating efuse fle requires launching the RTL platform, we generate them
        # only when the efuse map is different from the reference one.
        if not filecmp.cmp(local_efuse, ref_efuse):

            os.chdir(self.target.get_working_dir())

            path = 'pufgenerator'
            if not os.path.exists(path):
                shutil.copytree(f'{self.rtl_platform_path}'
                    '/../../fe/ips/pufsecurity/PSRT_022GW02B_B22A_v1.1.0', path)

            shutil.copyfile('efuse_preload.data', path + '/sim/efuse_preload.data')

            if os.path.exists(path + '/behv/EGP256X32/EGP256X32.dat'):
                os.remove(path + '/behv/EGP256X32/EGP256X32.dat')
            os.chdir(path + '/sim')


            if self.target.get_args().rtl_simulator == 'vsim':
                os.system('./run_vsim test_ext_otp_rw')
            else:
                os.system('./run_xcelium test_ext_otp_rw')

            shutil.copyfile('EGP256X32.dat', '../behv/EGP256X32/EGP256X32.dat')

            otp_path = '%s/pufgenerator/behv/EGP256X32' % \
                    self.target.get_working_dir()

        else:
            otp_path = self.target.get_file_path('gapylib/chips/gap/gap10')


        os.chdir(self.target.get_working_dir())

        for file in ['EGP256X32.dat', 'EGP256X32_F4.dat', 'EGP256X32_IF.dat',
                'EGP256X32_IF_LCK.dat', 'EGP256X32_IF_NLK.dat', 'EGP256X32_PUF.dat',
                'EGP256X32_PUF_F2.dat', 'EGP256X32_PUFORG.dat', 'EGP256X32_PUF_RN.dat',
                'EGP256X32_REP.dat', 'EGP256X32_REP_OK.dat', 'EGP256X32_TC.dat',
                'EGP256X32_TR.dat']:
            shutil.copyfile(f'{otp_path}/{file}', file)
