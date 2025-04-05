"""Helper for generating gap9_v2 efuse map"""

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


import typing



class EfuseField():
    """
    Parent class for all efuse fields, providing utility methods.

    A field is a subset of a 32bit bitfield.

    Attributes
    ----------
    name : str
        Name of the field.
    bit : int
        First bit of the field in the bitfield.
    width : int
        Width of the bitfield (number of bits).
    """

    def __init__(self, name: str, bit: int, width: int):
        self.name = name
        self.bit = bit
        self.width = width
        self.efuse = None

    def set(self, value):
        """Set the bitfield value.

        Parameters
        ----------
        value : int
            Value to be set.
        """
        self.efuse.set_field_value(value, self.bit, self.width)

    def get(self):
        """Get the bitfield value.

        Returns
        -------
        int
            The bitfield value.
        """
        return self.efuse.get_field_value(self.bit, self.width)

    def __str__(self):
        return f'{self.name}=0x{self.get():x}'


class Efuse():
    """
    Parent class for all efuse bitfields, providing utility methods.

    A bitfield is a 32bit efuse.

    Attributes
    ----------
    name : str
        Name of the field.
    efuse_id : int
        Id of the efuse in the whole efuse map.
    """

    fields = [
    ]

    def __init__(self, name, efuse_id):

        self.name = name
        self.efuse_id = efuse_id

        self.fields_dict = {}
        for field in self.fields:
            self.fields_dict[field.name] = field
            field.efuse = self

        self.value = 0


    def get_field(self, name):
        """Get an efuse bitfield from its name.

        Parameters
        ----------
        name : str
            Name of the efuse in the efuse map.

        Returns
        -------
        EfuseField
            The efuse.
        """
        field = self.fields_dict.get(name)
        if field is None:
            raise RuntimeError(f'Unknown efuse field (efuse: {self.name}, field: {name})')

        return field

    def get(self):
        """Get the efuse value.

        This returns the whole bitfield value, i.e. the concatenation of all fields.

        Returns
        -------
        int
            The efuse value.
        """
        return self.value

    def set(self, value):
        """Set the efuse value.

        This sets the whole bitfield value, i.e. the concatenation of all fields.

        Parameters
        ----------
        value : int
            The value of the efuse.
        """
        self.value = value

    def set_field_value(self, value, bit, width):
        """Set a field within the efuse.

        This should just be called by class EfuseField to update the field content within the
        whole bitfield value when the field value is modified.

        Parameters
        ----------
        value : int
            The value of the field.
        bit : int
            First bit of the field in the bitfield.
        width : int
            Width of the bitfield (number of bits).
        """
        self.value = (self.value & ~(((1<<width) - 1) << bit)) | (value << bit)

    def get_field_value(self, bit, width):
        """Get a field value within the efuse.

        This should just be called by class EfuseField to get the field content within the
        whole bitfield value.

        Parameters
        ----------
        bit : int
            First bit of the field in the bitfield.
        width : int
            Width of the bitfield (number of bits).

        Returns
        -------
        value : int
            The value of the field.
        """
        return (self.value >> bit) & ((1<<width) - 1)

    def __str__(self):
        result = f'{self.name}: value=0x{self.value}'

        if len(self.fields) != 0:
            fields_value = []
            for field in self.fields:
                fields_value.append(str(field))


            result += ' fields=( ' + ', '.join(fields_value) + ' )'

        return result


class Info1(Efuse):
    """
    Class for efuse info_1.
    """

    fields = [
        EfuseField('platform'                , 0,  3),
        EfuseField('bootmode'                , 3,  8),
        EfuseField('encrypted'               , 11, 1),
        EfuseField('wait_xtal'               , 12, 1),
        EfuseField('icache_enabled'          , 13, 1),
        EfuseField('fll_global_setup'        , 14, 1),
        EfuseField('fll_dco0_setup'          , 15, 1),
        EfuseField('uart_alive_wait_cycles'  , 16, 1),
        EfuseField('uart_password'           , 17,   1),
        EfuseField('uart_skip_pads'          , 18,   1),
        EfuseField('pmu_wait_reset_skip'     , 22, 1),
        EfuseField('timer_source'            , 23, 2),
        EfuseField('fast_clk_div_pow2_setup' , 25, 1),
        EfuseField('osc_ctrl_setup'          , 26, 1),
        EfuseField('mram_retb_wait'          , 27, 1),
        EfuseField('wake_mram_retb_wait'     , 28, 1),
        EfuseField('uart_conf'               , 29, 1),
        EfuseField('feature_disable_set'     , 30, 1),
        EfuseField('mram_reset_wait'         , 31, 1),
    ]


class Info2(Efuse):
    """
    Class for efuse info_2.
    """

    fields = [
        EfuseField('clkdiv_setup'            , 0, 1),
        EfuseField('clkdiv'                  , 1, 5),
        EfuseField('jtag_lock'               , 6, 1),
        EfuseField('ref_clk_wait'            , 7, 1),
        EfuseField('ref_clk_wait_deep_sleep' , 8, 1),
        EfuseField('bootmode0_nocheck'       , 9, 1),
        EfuseField('bootmode1_nocheck'       , 10, 1),
        EfuseField('mram_trim'               , 11, 1),
        EfuseField('wake_fast_clk_div_pow2_setup' , 12, 1),
        EfuseField('wake_osc_ctrl_setup'          , 13, 1),
        EfuseField('wake_wait_xtal'          , 17, 1),
        EfuseField('fll_wait'                , 18, 1),
        EfuseField('fll_wake_wait'           , 19, 1),
        EfuseField('pad_unlatch'             , 26, 1),
        EfuseField('mram_vref_wait'          , 28, 1),
        EfuseField('wake_mram_vref_wait'     , 29, 1),
        EfuseField('wake_mram_reset_wait'    , 30, 1),
    ]


class Info3(Efuse):
    """
    Class for efuse info_3.
    """

    fields = [
        EfuseField('flash_cs_setup'       , 0,   1),
        EfuseField('flash_cs'             , 1,   1),
        EfuseField('flash_itf_setup'      , 2,   1),
        EfuseField('flash_itf'            , 3,   2),
        EfuseField('flash_offset_setup'   , 5,   1),
        EfuseField('padfun0_setup'        , 6,   1),
        EfuseField('padfun1_setup'        , 7,   1),
        EfuseField('padfun2_setup'        , 8,   1),
        EfuseField('padfun3_setup'        , 9,   1),
        EfuseField('padfun4_setup'        , 10,   1),
        EfuseField('padfun5_setup'        , 11,   1),
        EfuseField('reprog0_setup'        , 12,  4),
        EfuseField('reprog1_setup'        , 13,  4),
        EfuseField('reprog2_setup'        , 14,  4),
        EfuseField('reprog3_setup'        , 15,  4),
        EfuseField('hyper_cs_polarity'    , 16,  5),
        EfuseField('flash_wait'           , 20,  1),
        EfuseField('flash_wakeup_wait'    , 30,  1),
    ]

class Padfun(Efuse):
    """
    Class for efuse Padfun.
    """

    def __init__(self, name, offset):
        self.fields = [
            EfuseField('pad0'            , 0 ,  2),
            EfuseField('pad1'            , 2 ,  2),
            EfuseField('pad2'            , 4 ,  2),
            EfuseField('pad3'            , 6 ,  2),
            EfuseField('pad4'            , 8 ,  2),
            EfuseField('pad5'            , 10,  2),
            EfuseField('pad6'            , 12,  2),
            EfuseField('pad7'            , 14,  2),
            EfuseField('pad8'            , 16,  2),
            EfuseField('pad9'            , 18,  2),
            EfuseField('pad10'           , 20,  2),
            EfuseField('pad11'           , 22,  2),
            EfuseField('pad12'           , 24,  2),
            EfuseField('pad13'           , 26,  2),
            EfuseField('pad14'           , 28,  2),
            EfuseField('pad15'           , 30,  2),
        ]

        super().__init__(name, offset)

class Muxgroup(Efuse):
    """
    Class for efuse Muxgroup.
    """

    def __init__(self, name, offset):
        self.fields = [
            EfuseField('mux_group0'            , 0 ,  6),
            EfuseField('mux_group1'            , 6 ,  6),
            EfuseField('mux_group2'            , 12 ,  6),
            EfuseField('mux_group3'            , 18 ,  6),
            EfuseField('mux_group4'            , 24 ,  6),
        ]

        super().__init__(name, offset)


class SecureBoot(Efuse):
    """
    Class for efuse info_3.
    """

    fields = [
        EfuseField('secure_only'          , 0,   1),
        EfuseField('aes_en'               , 1,   1),
        EfuseField('aes_key_size'         , 2,   1),
        EfuseField('crc_en'               , 3,   1),
        EfuseField('key_addr'             , 4,   12),
    ]

class UartConf(Efuse):
    """
    Class for efuse uart_conf.
    """

    fields = [
        EfuseField('parity_ena'          , 0,   1),
        EfuseField('bit_length'          , 1,   2),
        EfuseField('stop_bits'           , 3,   1),
        EfuseField('crc'                 , 4,   1),
        EfuseField('ref_clk_mux'         , 5,   1),
        EfuseField('cts_en'              , 10,   1),
        EfuseField('rts_en'              , 11,   1),
        EfuseField('tx_clk_en'           , 12,   1),
        EfuseField('tx_clk_pol'          , 13,   1),
        EfuseField('tx_clk_pha'          , 14,   1),
        EfuseField('clkdiv'              , 16,   1),
    ]

class Info4(Efuse):
    """
    Class for efuse info_4.
    """

    fields = [
        EfuseField('neva_cfg'                   , 10,   1),
    ]





class EfuseMap():
    """
    Class for whole efuse map.
    """

    efuses = [
        Info1 ( 'info_1'                          , 0),
        Info2 ( 'info_2'                          , 1),
        Info3 ( 'info_3'                          , 2),
        Efuse  ( 'uart_alive_wait_cycles'         , 3),
        Muxgroup  ( 'reprog_pad0'                 , 5),
        Muxgroup  ( 'reprog_pad1'                 , 6),
        Muxgroup  ( 'reprog_pad2'                 , 7),
        Muxgroup  ( 'reprog_pad3'                 , 8),
        Efuse  ( 'feature_disable'                , 9),
        SecureBoot  ( 'secure_boot'               , 10),
        UartConf  ( 'uart_conf'                   , 11),
        Efuse  ( 'uart_password_l'                , 12),
        Efuse  ( 'uart_password_h'                , 13),
        Padfun  ( 'padfun0'                       , 14),
        Padfun  ( 'padfun1'                       , 15),
        Padfun  ( 'padfun2'                       , 16),
        Padfun  ( 'padfun3'                       , 17),
        Padfun  ( 'padfun4'                       , 18),
        Padfun  ( 'padfun5'                       , 19),
        Efuse  ( 'wait_xtal_period'               , 20),
        Efuse  ( 'wait_xtal_delta'                , 21),
        Efuse  ( 'wait_xtal_min'                  , 22),
        Efuse  ( 'wait_xtal_max'                  , 23),
        Efuse  ( 'ref_clk_wait_cycles'            , 24),
        Efuse  ( 'ref_clk_wait_cycles_deep_sleep' , 25),
        Efuse  ( 'fast_clk_div_pow2'              , 26),
        Efuse  ( 'fll_drr'                        , 27),
        Efuse  ( 'fll_ccr1_pre_lock'              , 28),
        Efuse  ( 'fll_ccr1_post_lock'             , 29),
        Efuse  ( 'fll_ccr2'                       , 30),
        Efuse  ( 'fll_f0cr1'                      , 31),
        Efuse  ( 'fll_f0cr2'                      , 32),
        Efuse  ( 'wake_fast_clk_div_pow2'         , 33),
        Efuse  ( 'mram_reset_wait_cycles'         , 34),
        Efuse  ( 'wake_mram_reset_wait_cycles'    , 35),
        Efuse  ( 'fll_wait_cycles'                , 36),
        Efuse  ( 'fll_wake_wait_cycles'           , 37),
        Efuse  ( 'flash_wait'                     , 38),
        Efuse  ( 'flash_wakeup_wait'              , 39),
        Info4 ( 'info_4'                          , 40),
        Efuse  ( 'neva_cfg'                       , 41),
        Efuse  ( 'mram_trim'                      , 42),
        Efuse  ( 'flash_offset'                   , 43),
        Efuse  ( 'osc_ctrl'                       , 44),
        Efuse  ( 'wake_osc_ctrl'                  , 45),
        Efuse  ( 'mram_vref_wait_cycles'          , 46),
        Efuse  ( 'wake_mram_vref_wait_cycles'     , 47),
        Efuse  ( 'mram_retb_wait_cycles'          , 48),
        Efuse  ( 'wake_mram_retb_wait_cycles'     , 49),
        Efuse  ( 'pad_unlatch'                    , 50),
        Efuse  ( 'aes_key0'                       , 51),
        Efuse  ( 'aes_key1'                       , 52),
        Efuse  ( 'aes_key2'                       , 53),
        Efuse  ( 'aes_key3'                       , 54),
        Efuse  ( 'aes_key4'                       , 55),
        Efuse  ( 'aes_key5'                       , 56),
        Efuse  ( 'aes_key6'                       , 57),
        Efuse  ( 'aes_key7'                       , 58),
        Efuse  ( 'aes_iv0'                       , 59),
        Efuse  ( 'aes_iv1'                       , 60),
        Efuse  ( 'aes_iv2'                       , 61),
        Efuse  ( 'aes_iv3'                       , 62),
    ]

    nb_regs = 128


    def __init__(self):
        self.efuses_dict = {}
        self.efuses_list = [Efuse('empty', -1)] * self.nb_regs
        for efuse in self.efuses:
            self.efuses_dict[efuse.name] = efuse
            self.efuses_list[efuse.efuse_id] = efuse


    def apply_from_config(self, config: dict):
        """Computes the efuse values depending on specified config.

        The config is a set of properties describing the use-case for which to generate the efuse
        map.

        Parameters
        ----------
        config : dict
            Usecase configuration.
        """

        efuses_conf  = config.get('content')

        if efuses_conf is not None:
            for name, value in efuses_conf.items():
                if isinstance(value, dict):
                    for field_name, field_value in value.items():
                        self.get_efuse(name).get_field(field_name).set(int(field_value, 0))
                else:
                    self.get_efuse(name).set(int(value, 0))


    def get_efuse(self, name: str) -> EfuseField:
        """Get efuse from name.

        Parameters
        ----------
        name : str
            Efuse name.

        Returns
        -------
        EfuseField
            The efuse.
        """

        efuse = self.efuses_dict.get(name)
        if efuse is None:
            raise RuntimeError(f'Unknown efuse (name: {name})')

        return efuse


    def __str__(self):
        result = ''
        for efuse in self.efuses:
            result += str(efuse) + '\n'
        return result


    def gen_c_struct(self, name: str, file_desc: typing.TextIO):
        """Generate the efuse map into a C structure.

        This is used for the fuser.

        Parameters
        ----------
        name : str
            Name of the structure.
        file_desc : str
            File descriptor where to dump the structure.
        """

        file_desc.write('typedef struct\n')
        file_desc.write('{\n')
        file_desc.write('    unsigned int id;\n')
        file_desc.write('    unsigned int val;\n')
        file_desc.write('}pi_fuser_reg_t;\n')
        file_desc.write('\n')
        file_desc.write(f'pi_fuser_reg_t {name}[] = {{\n')
        for reg_id in range (0, self.nb_regs):
            value = self.efuses_list[reg_id].get()
            if value != 0:
                file_desc.write(f'    {{ .id={reg_id}, .val=0x{value} }},\n')

        file_desc.write('};\n')



    def gen(self, filename: str):
        """Generate the efuse map into a binary file.

        Parameters
        ----------
        filename : str
            Path of the file where to generate the efuse map.
        """

        # traces.info('  Generating to file: ' + filename)

        with open(filename, 'w', encoding='UTF-8') as file:
            for reg_id in range (0, self.nb_regs):
                value = self.efuses_list[reg_id].get()
                #traces.info('  Writing register (index: %d, value: 0x%x)' % (reg_id, value))
                # file.write('{0:032b}\n'.format(value))
                file.write(f'{value:032b}\n')
