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
        EfuseField('padfun0_setup'           , 16, 1),
        EfuseField('padfun1_setup'           , 17, 1),
        EfuseField('padfun2_setup'           , 18, 1),
        EfuseField('padfun3_setup'           , 19, 1),
        EfuseField('padfun4_setup'           , 20, 1),
        EfuseField('padfun5_setup'           , 21, 1),
        EfuseField('pmu_wait_reset_skip'     , 22, 1),
        EfuseField('timer_source'            , 23, 2),
        EfuseField('fast_clk_div_pow2_setup' , 25, 1),
        EfuseField('osc_ctrl_setup'          , 26, 1),
        EfuseField('osc_ctrl'                , 27, 3),
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
        EfuseField('wake_osc_ctrl'                , 14, 2),
        EfuseField('spi_conf_wait'           , 16, 1),
        EfuseField('wake_wait_xtal'          , 17, 1),
        EfuseField('fll_wait'                , 18, 1),
        EfuseField('fll_wake_wait'           , 19, 1),
        EfuseField('flash_status_set'        , 21, 2),
        EfuseField('flash_commands_set'      , 23, 1),
        EfuseField('flash_latency_set'       , 24, 1),
        EfuseField('flash_latency_value'     , 25, 5),
        EfuseField('wake_mram_reset_wait'    , 30, 1),
        EfuseField('keep_mram_on'            , 31, 1),
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
        EfuseField('hyper_delay_setup'    , 6,   1),
        EfuseField('hyper_delay'          , 7,   3),
        EfuseField('hyper_latency_setup'  , 10,  1),
        EfuseField('hyper_latency'        , 11,  5),
        EfuseField('hyper_cs_polarity'    , 16,  5),
        EfuseField('flash_wakeup'         , 17,  1),
        EfuseField('flash_reset'          , 18,  1),
        EfuseField('flash_init'           , 19,  1),
        EfuseField('flash_wait'           , 20,  1),
        EfuseField('flash_cmd_1'          , 21,  1),
        EfuseField('flash_cmd_2'          , 22,  1),
        EfuseField('flash_cmd_3'          , 23,  1),
        EfuseField('flash_cmd_4'          , 24,  1),
        EfuseField('flash_cmd_1_ds'       , 25,  1),
        EfuseField('flash_cmd_2_ds'       , 26,  1),
        EfuseField('flash_cmd_3_ds'       , 27,  1),
        EfuseField('flash_cmd_4_ds'       , 28,  1),
        EfuseField('flash_reset_wait'     , 29,  1),
        EfuseField('flash_wakeup_wait'    , 30,  1),
    ]


class Info4(Efuse):
    """
    Class for efuse info_4.
    """

    fields = [
        EfuseField('flash_gpio_pulse_gen'       , 0,   1),
        EfuseField('flash_gpio_pulse_wait'      , 1,   1),
        EfuseField('flash_gpio_pulse_pol'       , 2,   1),
        EfuseField('flash_gpio_pulse_id'        , 3,   7),
        EfuseField('neva_cfg'                   , 10,   1),
    ]


class Info5(Efuse):
    """
    Class for efuse info_5.
    """

    fields = [
        EfuseField('flash_pad'       , 3,  2),
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



class EfuseMap():
    """
    Class for whole efuse map.
    """

    efuses = [
        Info1 ( 'info_1'                         , 0),
        Info2 ( 'info_2'                         , 1),
        Info3 ( 'info_3'                         , 2),
        Efuse  ( 'fll_drr'                        , 3),
        Efuse  ( 'fll_ccr1_pre_lock'              , 4),
        Efuse  ( 'fll_ccr1_post_lock'             , 5),
        Efuse  ( 'fll_ccr2'                       , 6),
        Efuse  ( 'fll_f0cr1'                      , 7),
        Efuse  ( 'fll_f0cr2'                      , 8),
        Padfun ( 'padfun0'                        , 9),
        Padfun ( 'padfun1'                        , 10),
        Padfun ( 'padfun2'                        , 11),
        Padfun ( 'padfun3'                        , 12),
        Padfun ( 'padfun4'                        , 13),
        Padfun ( 'padfun5'                        , 14),
        Efuse  ( 'feature_disable'                , 15),
        Efuse  ( 'wait_xtal_period'               , 32),
        Efuse  ( 'wait_xtal_delta'                , 33),
        Efuse  ( 'wait_xtal_min'                  , 34),
        Efuse  ( 'wait_xtal_max'                  , 35),
        Efuse  ( 'ref_clk_wait_cycles'            , 36),
        Efuse  ( 'ref_clk_wait_cycles_deep_sleep' , 37),
        Efuse  ( 'fast_clk_div_pow2'              , 38),
        Efuse  ( 'wakeup_fll_drr'                 , 39),
        Efuse  ( 'wakeup_fll_ccr1_pre_lock'       , 40),
        Efuse  ( 'wakeup_fll_ccr1_post_lock'      , 41),
        Efuse  ( 'wakeup_fll_ccr2'                , 42),
        Efuse  ( 'wakeup_fll_f0cr1'               , 43),
        Efuse  ( 'wakeup_fll_f0cr2'               , 44),
        Efuse  ( 'wake_fast_clk_div_pow2'         , 45),
        Efuse  ( 'mram_reset_wait_cycles'         , 46),
        Efuse  ( 'wake_mram_reset_wait_cycles'    , 47),
        Efuse  ( 'spi_conf_wait_cycles'           , 48),
        Efuse  ( 'flash_offset'                   , 49),
        Efuse  ( 'fll_wait_cycles'                , 50),
        Efuse  ( 'fll_wake_wait_cycles'           , 51),
        Efuse  ( 'flash_reset_wait'               , 53),
        Efuse  ( 'flash_cmd_1'                    , 54),
        Efuse  ( 'flash_cmd_2'                    , 55),
        Efuse  ( 'flash_cmd_3'                    , 56),
        Efuse  ( 'flash_cmd_4'                    , 57),
        Efuse  ( 'flash_wait'                     , 58),
        Efuse  ( 'flash_wakeup_wait'              , 59),
        Efuse  ( 'flash_status'                   , 60),
        Efuse  ( 'flash_commands'                 , 61),
        Info4 ( 'info_4'                         , 62),
        Efuse  ( 'flash_gpio_pulse_wait'          , 63),
        Efuse  ( 'neva_cfg'                       , 64),
        Efuse  ( 'mram_trim_size'                 , 65),
        Efuse  ( 'mram_trim_start'                , 66),
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
            raise RuntimeError('Unknown efuse (name: {name})')

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
