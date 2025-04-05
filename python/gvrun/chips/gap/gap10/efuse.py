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
import logging
from gapylib.chips.gap.gap10 import efuse_generator
import gapylib.target


class EfuseGen():
    """
    Efuse generator for gap10 based on use-cases

    Attributes
    ----------
    target : gapylib.target
        Gapy target for which the efuse map is generated.

    path: str
        Path of the component for which the efuse is generated. Can be None if it is for the top
        component.

    """

    def __init__(self, target: gapylib.target, path: str=None):
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

            # Since we are going to override the padfun and mugroups, pad per pad, init them all
            # to default values
            for reg_id in range(0, 6):
                self.efuse_map.get_efuse(f'padfun{reg_id}').set(0x55555555)
            self.efuse_map.get_efuse('reprog_pad0').set(0x08184000)
            self.efuse_map.get_efuse('reprog_pad1').set(0x1032C289)
            self.efuse_map.get_efuse('reprog_pad2').set(0x185841D2)
            self.efuse_map.get_efuse('reprog_pad3').set(0x29A21B9B)

            pads_string = self.target.get_target_property('rom.pads')
            if pads_string is not None:
                for pad in pads_string.split(':'):
                    config, pad = pad.split('@')
                    pad_id = int(pad)
                    if config.find('alt') == 0:
                        alt_id = int(config[3:])
                        self.__set_padfun(pad_id, alt_id)
                    else:
                        print (config)
                        self.__set_reprogpad(pad_id, config)


            unlatch_config = self.target.get_target_property('rom.pad_unlatch')
            if unlatch_config is not None:
                self.efuse_map.get_efuse('pad_unlatch').set(unlatch_config)
                self.efuse_map.get_efuse('info_2').get_field('pad_unlatch').set(1)


            self.efuse_map.get_efuse('info_1').get_field('platform').set(2)  # RTL platform
            self.efuse_map.get_efuse('info_1').get_field('icache_enabled').set(1)

            # By default, only activate fast clock and fed other blocks like timer at 24Mhz/16
            fast_osc_freq_div = 24576062.0 / 16
            osc_ctrl = 1
            if self.target.get_target_property('rom.efuse.usecase.has_slow_ref_clock', self.path) \
                    == 'true':
                osc_ctrl |= 1 << 8
                osc_ctrl |= 1 << 11

            self.efuse_map.get_efuse('info_1').get_field('osc_ctrl_setup').set(1)
            self.efuse_map.get_efuse('osc_ctrl').set(osc_ctrl)
            self.efuse_map.get_efuse('info_1').get_field('fast_clk_div_pow2_setup').set(1)
            self.efuse_map.get_efuse('fast_clk_div_pow2').set(4 | (1<<3))
            self.efuse_map.get_efuse('info_2').get_field('wake_osc_ctrl_setup').set(1)
            self.efuse_map.get_efuse('wake_osc_ctrl').set(osc_ctrl)
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

            # Do not check bootmode pads by default to boot from what is specified in efuses
            pads_nocheck = 0 if \
                self.target.get_target_property('rom.efuse.skip_bootpads', self.path) == "false" \
                else 1
            self.efuse_map.get_efuse('info_2').get_field('bootmode0_nocheck').set(pads_nocheck)
            self.efuse_map.get_efuse('info_2').get_field('bootmode1_nocheck').set(pads_nocheck)

            boot_mode = self.target.get_target_property('boot.mode', self.path)

            if boot_mode == 'flash':
                self.__set_efuse_for_flash_boot(fast_osc_freq_div)

            elif boot_mode == 'jtag':
                self.efuse_map.get_efuse('info_1').get_field('bootmode').set(0)

            elif boot_mode == 'spislave':
                self.efuse_map.get_efuse('info_3').get_field('flash_itf_setup').set(1)
                self.efuse_map.get_efuse('info_3').get_field('flash_itf').set(
                    int(self.target.get_target_property('rom.efuse.usecase.boot_itf', self.path)))
                self.efuse_map.get_efuse('info_1').get_field('bootmode').set(4)

            if self.target.get_target_property('rom.uart.setup'):
                self.efuse_map.get_efuse('info_1').get_field('uart_conf').set(1)
                self.efuse_map.get_efuse('uart_conf').get_field('bit_length').set(3)
                self.efuse_map.get_efuse('uart_conf').get_field('stop_bits').set(1)
                self.efuse_map.get_efuse('uart_conf').get_field('clkdiv').set(
                    int(166000000 / 115200) - 1)
                self.efuse_map.get_efuse('info_1').get_field('uart_skip_pads').set(1)
                self.__set_padfun(57, 0)
                self.__set_padfun(58, 0)
                # FLow control pads are also set to allow dynamically enabling flow control
                self.__set_padfun(59, 0)
                self.__set_padfun(60, 0)

                self.efuse_map.get_efuse('info_3').get_field('flash_itf_setup').set(1)
                self.efuse_map.get_efuse('info_3').get_field('flash_itf').set(
                    int(self.target.get_target_property('rom.efuse.usecase.boot_itf', self.path)))

                if self.target.get_target_property('rom.uart.ctrl_flow'):
                    self.efuse_map.get_efuse('uart_conf').get_field('cts_en').set(1)
                    self.efuse_map.get_efuse('uart_conf').get_field('rts_en').set(1)

                if self.target.get_target_property('rom.uart.password') is not None:
                    password = int(self.target.get_target_property('rom.uart.password'), 0)
                    self.efuse_map.get_efuse('info_1').get_field('uart_password').set(1)
                    self.efuse_map.get_efuse('uart_password_l').set(password & 0xFFFFFFFF)
                    self.efuse_map.get_efuse('uart_password_h').set(password >> 32)

            self.efuse_map.get_efuse('info_1').get_field('uart_alive_wait_cycles').set(1)
            self.efuse_map.get_efuse('uart_alive_wait_cycles').set(
                math.ceil(0.001*fast_osc_freq_div))

            self.__set_efuse_fll()

        # self.efuse_map.apply_from_config(self.config)


    def __set_padfun(self, pad: int, fun: int):
        reg_id = int(pad / 16)
        reg_pad = pad % 16

        logging.debug('Adding pad function(pad: %d, reg: %d, index: %d, func: %d)',
            pad, reg_id, reg_pad, fun)

        self.efuse_map.get_efuse('info_3').get_field(f'padfun{reg_id}_setup').set(1)
        self.efuse_map.get_efuse(f'padfun{reg_id}').get_field(f'pad{reg_pad}').set(fun)

    def __set_reprogpad(self, pad: int, name: str):
        mux_groups = {
            "SPI0_CS0"               : 0x00, "SPI0_CS1"               : 0x01,
            "SPI0_CS2"               : 0x02, "SPI0_CS3"               : 0x03,
            "UART3_TX"               : 0x04, "UART3_RX"               : 0x05,
            "I2C0_SDA"               : 0x06, "I2C0_SCL"               : 0x07,
            "I2C1_SDA"               : 0x08, "CSI2_SDA"               : 0x09,
            "I2C1_SCL"               : 0x0A, "CSI2_SCL"               : 0x0B,
            "I2C2_SDA"               : 0x0C, "UART2_CTS"              : 0x0D,
            "I2C2_SCL"               : 0x0E, "UART2_RTS"              : 0x0F,
            "UART0_RX"               : 0x10, "UART0_TX"               : 0x11,
            "UART0_CTS"              : 0x12, "UART2_RX"               : 0x13,
            "UART0_RTS"              : 0x14, "UART2_TX"               : 0x15,
            "UART1_RX"               : 0x16, "PWM2"                   : 0x17,
            "PWM4"                   : 0x18, "UART1_TX"               : 0x19,
            "PWM3"                   : 0x1A, "PWM5"                   : 0x1B,
            "PWM0"                   : 0x1C, "UART1_CTS"              : 0x1D,
            "PWM6"                   : 0x1E, "PWM1"                   : 0x1F,
            "UART1_RTS"              : 0x20, "PWM7"                   : 0x21,
            "PMU_EXT_HYPER0_1P8V_PWR": 0x22, "PMU_EXT_HYPER1_1P8V_PWR": 0x23,
            "PMU_EXT_AIO_1P8V_PWR"   : 0x24, "PMU_EXT_EMRAM_1P8V_PWR" : 0x25,
            "PWM8"                   : 0x26, "PWM9"                   : 0x27,
            "PWM10"                  : 0x28, "PWM11"                  : 0x29,
            "PWM12"                  : 0x2A, "PWM13"                  : 0x2B,
            "PWM14"                  : 0x2C, "PWM15"                  : 0x2D,
            "SPI1_CS1"               : 0x2E, "SPI1_CS2"               : 0x2F,
            "SPI1_CS3"               : 0x30, "UART3_RTS"              : 0x31,
            "UART3_CTS"              : 0x32,
        }

        if pad >= 63:
            reg = 3
            index = pad - 63
        elif pad >= 62:
            reg = 2
            index = pad - 62 + 4
        elif pad >= 57:
            reg = 2
            index = pad - 57
        elif pad >= 34:
            reg = 1
            index = pad - 34
        elif pad >= 29:
            reg = 0
            index = pad - 29
        else:
            raise RuntimeError(f'Invalid reprogrammable pad (id: {pad})')

        mux_group = mux_groups.get(name.upper())

        if mux_group is None:
            raise RuntimeError(f'Invalid mux group: {name}')

        logging.debug('Adding reprogrammable pad setup(pad: %d, reg: %d, index: %d, mux_group: %d)',
            pad, reg, index, mux_group)

        self.efuse_map.get_efuse('info_3').get_field(f'reprog{reg}_setup').set(1)
        self.efuse_map.get_efuse(f'reprog_pad{reg}').get_field(f'mux_group{index}').set(mux_group)


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





    def __set_efuse_for_flash_boot(self, fast_osc_freq_div):
        # The device is for now hard-coded
        # It should come from the target flash descriptor
        if self.target.get_target_property('boot.flash_device', self.path) == 'mram':
            device_type = "mram"
        else:
            device_type = "spi"

        if device_type in [ 'hyper', 'spi' ]:
            itf = int(self.target.get_target_property('rom.efuse.flash.itf', self.path))
            flash_cs = int(self.target.get_target_property('rom.efuse.flash.cs', self.path))
            self.efuse_map.get_efuse('info_3').get_field('flash_cs_setup').set(1)
            self.efuse_map.get_efuse('info_3').get_field('flash_cs').set(flash_cs)
            self.efuse_map.get_efuse('info_3').get_field('flash_itf_setup').set(1)
            self.efuse_map.get_efuse('info_3').get_field('flash_itf').set(itf)

        if device_type == 'hyper':
            # Boot on UDMA hyper
            self.efuse_map.get_efuse('info_1').get_field('bootmode').set(1)
            self.efuse_map.get_efuse('info_2').get_field('clkdiv_setup').set(1)
            self.efuse_map.get_efuse('info_2').get_field('clkdiv').set(0)

        elif device_type == 'spi':
            # Boot on UDMA spi
            self.efuse_map.get_efuse('info_1').get_field('bootmode').set(6)
            self.efuse_map.get_efuse('info_2').get_field('clkdiv_setup').set(1)
            self.efuse_map.get_efuse('info_2').get_field('clkdiv').set(2)

        elif device_type == 'mram':
            # default key and iv for test purpose
            # manually swap bytes
            self.efuse_map.get_efuse('aes_key0').set(0x03020100)
            self.efuse_map.get_efuse('aes_key1').set(0x07060504)
            self.efuse_map.get_efuse('aes_key2').set(0x0b0a0908)
            self.efuse_map.get_efuse('aes_key3').set(0x0f0e0d0c)
            self.efuse_map.get_efuse('aes_key4').set(0x03020100)
            self.efuse_map.get_efuse('aes_key5').set(0x07060504)
            self.efuse_map.get_efuse('aes_key6').set(0x0b0a0908)
            self.efuse_map.get_efuse('aes_key7').set(0x0f0e0d0c)
            self.efuse_map.get_efuse('aes_iv0').set(0x03020100)
            self.efuse_map.get_efuse('aes_iv1').set(0x07060504)
            self.efuse_map.get_efuse('aes_iv2').set(0x0)
            self.efuse_map.get_efuse('aes_iv3').set(0x0)
            # get secure boot/aes related properties
            key_size =\
                int(self.target.get_target_property('rom.efuse.secure_boot.key_size', self.path))
            key_addr =\
                int(self.target.get_target_property('rom.efuse.secure_boot.key_addr', self.path))
            aes_en =\
                int(self.target.get_target_property('rom.efuse.secure_boot.enabled', self.path))
            aes_forced =\
                int(self.target.get_target_property('rom.efuse.secure_boot.forced', self.path))
            self.efuse_map.get_efuse('secure_boot').get_field('aes_en').set(aes_en)
            # if aes is forced (no unsafe boot possible anymore)
            self.efuse_map.get_efuse('secure_boot').get_field('secure_only').set(aes_forced)
            # key size default to 1, 256 bits
            self.efuse_map.get_efuse('secure_boot').get_field('aes_key_size').set(key_size)
            # key addr, default to 4CC in default fuse map
            # use 0x300 to use puf intrinsic key
            self.efuse_map.get_efuse('secure_boot').get_field('key_addr').set(key_addr)
            self.efuse_map.get_efuse('info_1').get_field('bootmode').set(3)
            self.efuse_map.get_efuse('info_1').get_field('mram_reset_wait').set(1)
            self.efuse_map.get_efuse('info_2').get_field('wake_mram_reset_wait').set(1)
            self.efuse_map.get_efuse('info_1').get_field('mram_retb_wait').set(1)
            self.efuse_map.get_efuse('info_1').get_field('wake_mram_retb_wait').set(1)
            self.efuse_map.get_efuse('info_2').get_field('mram_vref_wait').set(1)
            self.efuse_map.get_efuse('info_2').get_field('wake_mram_vref_wait').set(1)
            self.efuse_map.get_efuse('mram_reset_wait_cycles').set(
                math.ceil(0.000003*fast_osc_freq_div))
            self.efuse_map.get_efuse('wake_mram_reset_wait_cycles').set(
                math.ceil(0.000003*fast_osc_freq_div))

            self.efuse_map.get_efuse('mram_retb_wait_cycles').set(
                math.ceil(0))
            self.efuse_map.get_efuse('wake_mram_retb_wait_cycles').set(
                math.ceil(0))

            self.efuse_map.get_efuse('mram_vref_wait_cycles').set(
                math.ceil(0.000003*fast_osc_freq_div))
            self.efuse_map.get_efuse('wake_mram_vref_wait_cycles').set(
                math.ceil(0.000003*fast_osc_freq_div))

            self.efuse_map.get_efuse('info_2').get_field('clkdiv_setup').set(1)
            self.efuse_map.get_efuse('info_2').get_field('clkdiv').set(5)
            self.efuse_map.get_efuse('info_3').get_field('flash_wait').set(1)
            self.efuse_map.get_efuse('flash_wait').set(math.ceil(0.00002*fast_osc_freq_div))

    def gen_stim(self, filename: str):
        """Generate the efuse map to the specified stimuli file.

        Parameters
        ----------
        filename : str
            Path of the file where to generate the efuse map.
        """
        self.efuse_map.gen(filename)
