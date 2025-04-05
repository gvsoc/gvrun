"""
Helper for running RTL simulations on gap9_5
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

import gapylib.chips.gap.rtl_runner
import gapylib.target


class Runner(gapylib.chips.gap.rtl_runner.Runner):
    """
    Helper class for running execution on gap9_5 RTL platform.
    """


    def parse_args(self, args: any, gvsoc_cosim=None, gvsoc_config_path=None, full_config=None):
        super().parse_args(args, gvsoc_cosim=gvsoc_cosim, gvsoc_config_path=gvsoc_config_path,
            full_config=full_config)

        # Force to mram boot
        self.__set_arg('+VSIM_BOOTMODE_CFG=3')
        # self.__set_arg('+VIP_MODE=CUSTOM')
        # self.__set_arg('+ENABLE_HYPER0_CS1_PSRAM_VIP=1')
        # self.__set_arg('+ENABLE_HYPER0_CS0_MX25U51245G_VIP=1')
        self.__set_arg('+UVM_VERBOSITY=UVM_LOW')
        self.__set_arg('+UVM_TESTNAME=csi2_rx_pkt_raw8')
        self.__set_arg('+phy_sel=dphy')
        self.__set_arg('+lane=2lane')
        self.__set_arg('+data_width=8bit')
        self.__set_arg('+frame_mode=Gen')
