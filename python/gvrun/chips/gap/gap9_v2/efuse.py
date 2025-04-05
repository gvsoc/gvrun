"""Generates few default efuse configurations for gap9_v2"""

#
# Copyright (C) 2019 GreenWaves Technologies
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


import math
from gapylib.chips.gap.gap9_v2 import efuse_generator
import gapylib.target


class EfuseGen():
    """
    Efuse generator for gap9_v2 based on use-cases

    Attributes
    ----------
    target : gapylib.target
        Gapy target for which the efuse map is generated.

    path: str
        Path of the component for which the efuse is generated. Can be None if it is for the top
        component.
    """

    def __init__(self, target: gapylib.target, path:str=None):
        self.target = target
        self.efuse_map = None
        self.path = path

    def gen_efuse_map(self):
        """Generate the efuse map from the config.

        Parameters
        ----------
        filename : str
            Path of the file where to generate the efuse map.
        """
        # traces.info('Creating efuse stimuli')
        self.efuse_map = efuse_generator.EfuseMap()

        if self.target.get_target_property('rom.efuse.usecase.enabled', self.path) == 'true':
            self.__set_efuse_padfun()

            self.efuse_map.get_efuse('info_1').get_field('platform').set(2)  # RTL platform
            self.efuse_map.get_efuse('info_1').get_field('icache_enabled').set(1)

            # By default, only activate fast clock and fed other blocks like timer at 24Mhz/16
            fast_osc_freq_div = 24576062.0 / 16
            self.efuse_map.get_efuse('info_1').get_field('osc_ctrl_setup').set(1)
            self.efuse_map.get_efuse('info_1').get_field('osc_ctrl').set(1)
            self.efuse_map.get_efuse('info_1').get_field('fast_clk_div_pow2_setup').set(1)
            self.efuse_map.get_efuse('fast_clk_div_pow2').set(4 | (1<<3))
            self.efuse_map.get_efuse('info_2').get_field('wake_osc_ctrl_setup').set(1)
            self.efuse_map.get_efuse('info_2').get_field('wake_osc_ctrl').set(1)
            self.efuse_map.get_efuse('info_2').get_field('wake_fast_clk_div_pow2_setup').set(1)
            self.efuse_map.get_efuse('wake_fast_clk_div_pow2').set(4 | (1<<3))

            # Activate oscillator stability wait loop
            self.efuse_map.get_efuse('info_1').get_field('wait_xtal').set(1)
            # Xtal is monitored in open loop at max 50MHz and we want to monitor every 10us
            self.efuse_map.get_efuse('wait_xtal_period').set(500)
            self.efuse_map.get_efuse('wait_xtal_delta').set(10)    # Delta is 1%
            # Stop as soon as 5 stable periods are found
            self.efuse_map.get_efuse('wait_xtal_min').set(5)
            self.efuse_map.get_efuse('wait_xtal_max').set(50000)
            # Also put right values in fixed wait loop in case a test wants to activate it
            cycles = int(2000*fast_osc_freq_div/1000000)

            self.efuse_map.get_efuse('fll_wait_cycles').set(cycles) # 100us
            self.efuse_map.get_efuse('fll_wake_wait_cycles').set(cycles) # 100us

            # No wait for ref clock
            self.efuse_map.get_efuse('info_2').get_field('ref_clk_wait').set(1)
            self.efuse_map.get_efuse('ref_clk_wait_cycles').set(0)
            self.efuse_map.get_efuse('info_2').get_field('ref_clk_wait_deep_sleep').set(1)
            self.efuse_map.get_efuse('ref_clk_wait_cycles_deep_sleep').set(0)
            self.efuse_map.get_efuse('info_1').get_field('timer_source').set(2)

            # Enable JTAG
            self.efuse_map.get_efuse('info_1').get_field('feature_disable_set').set(1)
            self.efuse_map.get_efuse('feature_disable').set(0)

            boot_mode = self.target.get_target_property('boot.mode', self.path)
            if boot_mode == 'flash':
                self.__set_efuse_for_flash_boot(fast_osc_freq_div)

            elif boot_mode == 'jtag':
                self.efuse_map.get_efuse('info_2').get_field('bootmode0_nocheck').set(0)
                self.efuse_map.get_efuse('info_2').get_field('bootmode1_nocheck').set(0)

                self.efuse_map.get_efuse('info_1').get_field('bootmode').set(0)

            elif boot_mode == 'spislave':
                # Do not check bootmode pads by default to boot from what is specified in efuses
                self.efuse_map.get_efuse('info_2').get_field('bootmode0_nocheck').set(1)
                self.efuse_map.get_efuse('info_2').get_field('bootmode1_nocheck').set(1)

                self.efuse_map.get_efuse('info_1').get_field('bootmode').set(4)

            self.__set_efuse_fll()

        # This should now come from target properties
        # self.efuse_map.apply_from_config(self.config)



    def gen_stim(self, filename: str):
        """Generate the efuse map to the specified stimuli file.

        Parameters
        ----------
        filename : str
            Path of the file where to generate the efuse map.
        """
        self.efuse_map.gen(filename)


    def __set_efuse_padfun(self):
        # Set all padfun to 1 by default except for JTAG pads to reflect edfault HW values
        for i in range(0, 96):
            #self.__set_padfun(efuses, i,  1)
            self.__set_padfun(i,  0)  # Temporary put to 0 to not break all tests

        self.__set_padfun(81,  0)
        self.__set_padfun(82,  0)
        self.__set_padfun(83,  0)
        self.__set_padfun(84,  0)
        self.__set_padfun(85,  0)


    def __set_padfun(self, pad: int, fun: int):
        reg_id = int(pad / 16)
        reg_pad = pad % 16

        self.efuse_map.get_efuse('info_1').get_field(f'padfun{reg_id}_setup').set(1)
        self.efuse_map.get_efuse(f'padfun{reg_id}').get_field(f'pad{reg_pad}').set(fun)


    def __set_efuse_for_flash_boot(self, fast_osc_freq_div):
        # The device is for now hard-coded
        # It should come from the target flash descriptor
        if self.target.get_target_property('boot.flash_device', self.path) == 'mram':
            device_type = "mram"
        else:
            device_type = "hyper"

        # Do not check bootmode pads by default to boot from what is specified in efuses
        pads_nocheck = 0 if self.target.get_target_property(
            'rom.efuse.skip_bootpads', self.path) == "false" else 1
        self.efuse_map.get_efuse('info_2').get_field('bootmode0_nocheck').set(pads_nocheck)
        self.efuse_map.get_efuse('info_2').get_field('bootmode1_nocheck').set(pads_nocheck)

        if device_type == 'hyper':
            # Boot on UDMA hyper
            self.efuse_map.get_efuse('info_3').get_field('flash_cs_setup').set(1)
            self.efuse_map.get_efuse('info_3').get_field('flash_cs').set(1)
            self.efuse_map.get_efuse('info_3').get_field('flash_itf_setup').set(1)
            self.efuse_map.get_efuse('info_3').get_field('flash_itf').set(0)
            self.efuse_map.get_efuse('info_1').get_field('bootmode').set(1)
            self.efuse_map.get_efuse('info_2').get_field('clkdiv_setup').set(1)
            self.efuse_map.get_efuse('info_2').get_field('clkdiv').set(0)
            # Pads for hyper 0
            self.__set_padfun(0,  0)
            self.__set_padfun(1,  0)
            self.__set_padfun(2,  0)
            self.__set_padfun(3,  0)
            self.__set_padfun(4,  0)
            self.__set_padfun(5,  0)
            self.__set_padfun(6,  0)
            self.__set_padfun(7, 0)
            self.__set_padfun(8, 0)
            self.__set_padfun(9, 0)
            self.__set_padfun(10, 0)
            self.__set_padfun(11, 0)
            self.__set_padfun(12, 0)


        elif device_type == 'spi':
            self.__set_efuse_boot_spi(fast_osc_freq_div)

        elif device_type == 'mram':
            # Boot on MRAM
            self.efuse_map.get_efuse('info_1').get_field('bootmode').set(3)
            self.efuse_map.get_efuse('info_1').get_field('mram_reset_wait').set(1)
            self.efuse_map.get_efuse('info_2').get_field('wake_mram_reset_wait').set(1)
            self.efuse_map.get_efuse('mram_reset_wait_cycles').set(
                math.ceil(0.000003*fast_osc_freq_div))
            self.efuse_map.get_efuse('wake_mram_reset_wait_cycles').set(
                math.ceil(0.000003*fast_osc_freq_div))
            self.efuse_map.get_efuse('info_2').get_field('clkdiv_setup').set(1)
            self.efuse_map.get_efuse('info_2').get_field('clkdiv').set(5)
            self.efuse_map.get_efuse('info_3').get_field('flash_wait').set(1)
            self.efuse_map.get_efuse('flash_wait').set(math.ceil(0.00002*fast_osc_freq_div))

    def __set_efuse_fll(self):
        # Lock FLL soc and periph
        self.efuse_map.get_efuse('info_1').get_field('fll_global_setup').set(1)
        self.efuse_map.get_efuse('info_1').get_field('fll_dco0_setup').set(1)
        # FLL DRR (DCO min | DCO max)
        self.efuse_map.get_efuse('fll_drr').set((0 << 0) | (0x1ff << 16))
        # Pre-lock FLL CCR1 (CLK0 DIV | CLK1 DIV)
        self.efuse_map.get_efuse('fll_ccr1_pre_lock').set((0 << 0) | (0 << 8))
        # Post-lock FLL CCR1 (CLK0 DIV | CLK1 DIV)
        self.efuse_map.get_efuse('fll_ccr1_post_lock').set((0 << 0) | (3 << 8))
        # FLL CCR2 (CLK0 SEL | CLK1 SEL | CLK2_SEL | CLK3_SEL | CKG0)
        self.efuse_map.get_efuse('fll_ccr2').set(
            (0x1 << 0) | (0x1 << 4) | (0x1 << 8) | (0x2 << 12) | (1 << 16))
        # DCO0 CR1 (DCO EN | CLOSE LOOP | LOOP GAIN | LOCK TOL | ITG | ASSERT CYCLES)
        self.efuse_map.get_efuse('fll_f0cr1').set(
            (1 << 0) | (1 << 1) | (4 << 4) | (10 << 8) | (24 << 16) | (6 << 26))
        # DCO0 CR2 (MFI | DCO CODE)
        self.efuse_map.get_efuse('fll_f0cr2').set((166 << 0) | (0x1A << 16))

        # FLL DRR (DCO min | DCO max)
        self.efuse_map.get_efuse('wakeup_fll_drr').set((0 << 0) | (0x1ff << 16))
        # Pre-lock FLL CCR1 (CLK0 DIV | CLK1 DIV)
        self.efuse_map.get_efuse('wakeup_fll_ccr1_pre_lock').set((0 << 0) | (0 << 8))
        # Post-lock FLL CCR1 (CLK0 DIV | CLK1 DIV)
        self.efuse_map.get_efuse('wakeup_fll_ccr1_post_lock').set((0 << 0) | (1 << 8))
        # FLL CCR2 (CLK0 SEL | CLK1 SEL | CLK2_SEL | CLK3_SEL | CKG0)
        self.efuse_map.get_efuse('wakeup_fll_ccr2').set(
            (0x1 << 0) | (0x1 << 4) | (0x1 << 8) | (0x2 << 12) | (1 << 16))
        # DCO0 CR1 (DCO EN | CLOSE LOOP | LOOP GAIN | LOCK TOL | ITG | ASSERT CYCLES)
        self.efuse_map.get_efuse('wakeup_fll_f0cr1').set(
            (1 << 0) | (1 << 1) | (4 << 4) | (10 << 8) | (24 << 16) | (6 << 26))
        # DCO0 CR2 (MFI | DCO CODE)
        self.efuse_map.get_efuse('wakeup_fll_f0cr2').set((166 << 0) | (0x1A << 16))


    def __set_efuse_boot_spi(self, fast_osc_freq_div):
        # Boot on UDMA spi
        self.efuse_map.get_efuse('info_1').get_field('bootmode').set(2)
        self.efuse_map.get_efuse('info_2').get_field('clkdiv_setup').set(1)
        self.efuse_map.get_efuse('info_2').get_field('clkdiv').set(0)
        # Flash is on CS 0 ITF 1 (CS is inverted in efuse)
        self.efuse_map.get_efuse('info_3').get_field('flash_cs_setup').set(1)
        self.efuse_map.get_efuse('info_3').get_field('flash_cs').set(1)
        self.efuse_map.get_efuse('info_3').get_field('flash_itf_setup').set(1)
        self.efuse_map.get_efuse('info_3').get_field('flash_itf').set(1)

        # SPI wait time after configuring control register, should take 200ns but
        # RTL model take 10us to update it
        self.efuse_map.get_efuse('info_2').get_field('spi_conf_wait').set(1)
        self.efuse_map.get_efuse('spi_conf_wait_cycles').set(
            math.ceil(0.00001*fast_osc_freq_div))

        # SPI status register value
        self.efuse_map.get_efuse('info_2').get_field('flash_status_set').set(2)
        # Activate octospi modeand DTR and unprotect all sectors
        self.efuse_map.get_efuse('flash_status').set(0x1b880200)

        # SPI flash latency
        self.efuse_map.get_efuse('info_2').get_field('flash_latency_set').set(1)
        self.efuse_map.get_efuse('info_2').get_field('flash_latency_value').set(22)

        # Flash commands
        self.efuse_map.get_efuse('info_2').get_field('flash_commands_set').set(1)
        self.efuse_map.get_efuse('flash_commands').set(
            (0x06 << 0) | (0x71 << 8) | (0x0B << 16) | (0xAB << 24))
