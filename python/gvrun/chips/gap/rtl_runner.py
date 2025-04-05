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

import os.path
import argparse
import logging
import gapylib.target
import gapylib.chips.gap.rtl_testbench as testbench



class Runner():
    """
    Helper class for running execution on gap9_v2 RTL platform.

    Attributes
    ----------
    target : gapylib.target.Target
        The target on which the execution is run.
    """

    def __init__(self, target: gapylib.target.Target):
        self.target = target
        # List of environment variables required by the RTL platform in the terminal launching
        # the platform
        self.env = {}
        # List of arguments required on the RTL platform command-line
        self.args = []

        self.rtl_platform_path = None
        self.rtl_platform_sim_path = None


    @staticmethod
    def append_args(parser: argparse.ArgumentParser):
        """Append runner specific arguments to gapy command-line.

        This is used to append arguments only if the RTL platform is selected.

        Parameters
        ----------
        parser : argparse.ArgumentParser
            The parser where to add arguments.
        """

        default_rtl_sim = os.environ.get('CONFIG_GAPY_DEFAULT_RTL_SIMULATOR')
        default_rtl_sim = 'xcelium' if default_rtl_sim is None else default_rtl_sim

        parser.add_argument("--gui", dest="gui", action="store_true",
            help="launch the RTL simulator in GUI mode")

        parser.add_argument("--power-dump", dest="power", action="store_true",
            help="launch the RTL simulator with VCD dumping for power estimation")

        parser.add_argument("--rtl-simulator", dest="rtl_simulator", default=default_rtl_sim,
            choices=['xcelium', 'vsim'],
            type=str, help="specify the simulator used for RTL simulation")

        parser.add_argument("--rtl-verbosity", dest="rtl_verbosity", default=-1,
            type=int, help="specify the RTL simulator verbosity")

        parser.add_argument("--rtl-ocd-bitbang-port", dest="rtl_ocd_bitbang_port", default=-1,
            type=int, help="specify the RTL Openocd bitbang port")

        parser.add_argument("--rtl-platform-path", dest="rtl_platform_path",
            type=str, help="specify the platform path used for RTL simulation")

        parser.add_argument("--rtl-platform-sim-path", dest="rtl_platform_sim_path",
            type=str, help="specify the platform simulation path used for RTL simulation")

        parser.add_argument("--rtl-arg", dest="rtl_args", action="append", default=[],
            help="add platform argument")

        [args, _] = parser.parse_known_args()

        if args.rtl_simulator == 'xcelium':
            parser.add_argument("--xcelium-root", dest="xcelium_root",
                type=str, help="specify the path to Xcelium simulator")

        if args.rtl_simulator == 'vsim':
            parser.add_argument("--vsim-dpi-cpp-path", dest="dpi_cpp_path", default=None,
                type=str, help="specify DPI C++ compiler path")

        if args.rtl_simulator == 'vsim' and args.gui is True:
            parser.add_argument("--use-default-gui", dest="use_default_gui", action="store_true",
                help="Use questa visualizer instead of legacy gui.\
                Currenly off by default to keep compat with older questa versions")


    def parse_args(self, args: any, gvsoc_cosim=None, gvsoc_config_path=None, full_config=None):
        """Handle arguments.

        This will mostly use the arguments to prepare the platform command.

        Parameters
        ----------
        args :
            The arguments.
        """
        _ = full_config

        if args.rtl_platform_path is None:
            raise RuntimeError('the following arguments are required: --rtl-platform-path')

        if args.rtl_platform_sim_path is None:
            raise RuntimeError('the following arguments are required: --rtl-platform-sim-path')

        if args.rtl_simulator == 'xcelium':
            if args.xcelium_root is None:
                args.xcelium_root = os.environ.get('XCELIUM_ROOT')

            if args.xcelium_root is None:
                raise RuntimeError('the following arguments are required: --xcelium-root')

        # Save platform path since upper clas might have override the one in args and might be
        # cleared if we parse again arguments
        self.rtl_platform_path = args.rtl_platform_path
        self.rtl_platform_sim_path = args.rtl_platform_sim_path

        # Don't know if it is really needed, seems to enable some design introspection
        self.__set_env('VOPT_ACC_ENA', 'YES')
        # We always generate an mram stimuli file
        self.__set_arg('+PRELOAD_MRAM=1')
        # DPI wrapper for openocd connection
        self.__set_arg('-sv_lib')
        self.__set_arg(f'{self.rtl_platform_path}/ips_inputs/dpi/librbs')
        # Testbench verbosity
        self.__set_arg(f'+TB_DEBUG_VERBOSITY={args.rtl_verbosity}')

        # DPI wrapper for GVSOC mode where gvsoc is providing device models
        if gvsoc_cosim is not None:

            dpi_path = f'{gvsoc_cosim}/lib/libgvsocdpi'

            if not os.path.exists(dpi_path + '.so'):
                raise RuntimeError('Did no find DPI models: ' + dpi_path + '.so')

            self.__set_arg('-sv_lib')
            self.__set_arg('%s' % dpi_path)

            self.__set_arg(f'+DPI_CONFIG_FILE={gvsoc_config_path}')
        else:
            # Case where models are not used, we just connect an empty wrapper to avoir the
            # platform to complain
            dpi_path = os.path.join(self.rtl_platform_path, 'ips_inputs/dpi/libchipwrapper')
            self.__set_arg(f'-sv_lib {dpi_path}')

        if args.rtl_ocd_bitbang_port != -1:
            self.__set_arg('+OPENOCD_PORT=%d' % args.rtl_ocd_bitbang_port)


        # Append all arguments given on the command-line
        self.args += args.rtl_args


    def image(self):
        """Handle the gapy command 'image' to produce the target images.

        This is used on RTL platform to generate preloading files for flash and efuse.

        """
        # Go through all flashes and generate a preloading file.
        for flash in self.target.flashes.values():
            self.__gen_flash_stimuli(flash)

        if self.target.get_target_property('boot.mode') in ['jtag', 'spislave'] or \
            self.target.get_target_property('boot.mode_on_pads') in ['jtag']:
            testbench.gen_jtag_stimuli(self.target.get_args().binary,
                self.target.get_abspath('slm_files/l2_stim.slm'))


    def traces(self):
        """Add debug information to RTL platform traces.
        """
        traces = [
            'trace_core_00_9.log', 'trace_core_00_0.log', 'trace_core_00_1.log',
            'trace_core_00_2.log', 'trace_core_00_3.log', 'trace_core_00_4.log',
            'trace_core_00_5.log', 'trace_core_00_6.log', 'trace_core_00_7.log',
            'trace_core_00_8.log'
        ]

        args = self.target.get_args()
        binary = args.binary
        rom_binary = '%s/boot/boot-gap9' % self.rtl_platform_path

        os.chdir(self.target.get_working_dir())

        for trace in traces:
            out_trace = f'extended_{trace}'
            if os.path.exists(trace):
                trace_cmd = f'gap-rtl-trace-extend --binary {binary} --binary {rom_binary}' \
                    f' --input {trace} --output {out_trace}'

                logging.debug('Generating extended trace file with command:')
                logging.debug('  %s', trace_cmd)

                error = os.system(trace_cmd)

                if error != 0:
                    raise RuntimeError(f'The board returned an error: {error:d}')


    def get_command(self) -> str:
        """Returns the platform run command.

        This command is the one which should be executed to run the target.

        Returns
        -------
        str
            The command.
        """
        command = self.__get_platform_cmd()
        self.__create_symlinks()
        return command


    def run(self):
        """Handle the gapy command 'run' to start execution on the platform.
        """
        os.chdir(self.target.get_working_dir())

        command = ' '.join(self.get_command())

        print ('Launching simulator with command:')
        print (command)

        error = os.system(command)

        if error != 0:
            raise RuntimeError(f'RTL platform returned an error: {error:d}')


    def __gen_section_stimuli(self, buff, offset, file_desc, stim_format):
        if stim_format == 'mram':
            last_bytes = len(buff) & 0xF
            offset = offset >> 4
            for i in range(0, 16 - last_bytes):
                buff.append(0)
            for i in range(0, len(buff) >> 4):

                value = (buff[i * 16 + 15] << 120) + (buff[i * 16 + 14] << 112) + \
                        (buff[i * 16 + 13] << 104) + (buff[i * 16 + 12] << 96) + \
                        (buff[i * 16 + 11] << 88)  + (buff[i * 16 + 10] << 80) + \
                        (buff[i * 16 + 9]  << 72)  + (buff[i * 16 + 8]  << 64) + \
                        (buff[i * 16 + 7]  << 56)  + (buff[i * 16 + 6]  << 48) + \
                        (buff[i * 16 + 5]  << 40)  + (buff[i * 16 + 4]  << 32) + \
                        (buff[i * 16 + 3]  << 24)  + (buff[i * 16 + 2]  << 16) + \
                        (buff[i * 16 + 1]  << 8)   + (buff[i * 16])
                file_desc.write("@%08X %32X\n" % (offset + i, value))

        elif stim_format == 'slm_16':
            offset = offset >> 1

            if len(buff) & 1 != 0:
                buff.append(0)
            for i in range(0, len(buff) >> 1):
                value = (buff[i * 2 + 1] << 8) + buff[i * 2]
                file_desc.write("@%08X %04X\n" % (offset + i, value))

        elif stim_format == 'slm_8':
            for i, elem in enumerate(buff):
                file_desc.write("@%08X %02X\n" % (offset + i, elem))

        else:
            raise RuntimeError(f'Unknown SLM format: {stim_format}')


    def __gen_flash_stimuli(self, flash):

        stim_format = flash.get_flash_attribute('rtl_stim_format')
        stim_name = flash.get_flash_attribute('rtl_stim_name')

        stim_path = self.target.get_abspath(stim_name)

        os.makedirs(os.path.dirname(stim_path), exist_ok=True)

        with open(stim_path, 'wt', encoding='utf-8') as file_desc:
            for section in flash.get_sections():
                if not section.is_empty() or section.get_offset() == 0:
                    self.__gen_section_stimuli(
                        section.get_image(), section.get_offset(), file_desc, stim_format)



    def __create_symlinks(self):

        args = self.target.get_args()
        plt_path = self.rtl_platform_path
        sim_path = self.rtl_platform_sim_path

        if args.rtl_simulator == 'vsim':
            self.__create_symlink(plt_path, 'boot')
            self.__create_symlink(plt_path, 'modelsim.ini')
            self.__create_symlink(plt_path, 'work')
            self.__create_symlink(plt_path, 'tcl_files')
            self.__create_symlink(plt_path, 'waves')
            self.__create_symlink(plt_path, 'models')
            self.__create_symlink(plt_path, 'ips_inputs')
        else:
            self.__create_symlink(plt_path, 'boot')
            self.__create_symlink(plt_path, 'ips_inputs')
            self.__create_symlink(plt_path, 'models')
            self.__create_symlink(plt_path, 'tcl_files')
            self.__create_symlink(plt_path, 'cds.lib')
            self.__create_symlink(plt_path, 'hdl.var')
            self.__create_symlink(plt_path, 'waves')
            self.__create_symlink(plt_path, 'xcsim_libs')
            self.__create_symlink(plt_path, 'min_access.txt')
            self.__create_symlink(plt_path, 'scripts')
            self.__create_symlink(sim_path, 'scripts', 'sim_scripts')

            if os.system('xmsdfc models/s27ks0641/bmod/s27ks0641.sdf'):
                raise RuntimeError('Failed to init sdf file')

            if os.system('xmsdfc models/s26ks512s/bmod/s26ks512s.sdf'):
                raise RuntimeError('Failed to init sdf file')

            if os.system('xmsdfc models/s26ks512s/bmod/s26ks512s.sdf'):
                raise RuntimeError('Failed to init sdf file')


    @staticmethod
    def __create_symlink(rtl_path, name, symname=None):

        if symname is None:
            symname = name

        if os.path.islink(symname):
            os.remove(symname)

        os.symlink(os.path.join(rtl_path, name), symname)


    def __get_platform_cmd(self):

        args = self.target.get_args()

        if not os.path.exists(self.rtl_platform_path):
            raise RuntimeError(f"ERROR: rtl platform path does not exist: {self.rtl_platform_path}")

        command = []

        if self.target.get_args().rtl_simulator == 'vsim':
            if args.gui and args.use_default_gui is True:
                self.__set_env('gui_vis', '1')

        # for key, value in self.env.items():
        #     command += [
        #         f'export {key}="{value}" &&'
        #     ]

        # Create a stub script whose roles is to export envvar as they cannot be properly passed
        # to subprocess
        stub_script = os.path.join(self.target.get_working_dir(), 'rtl_stub')

        with open(stub_script, 'w', encoding="utf-8") as file:
            file.write ('#!/usr/bin/env bash\n')

            for key, value in self.env.items():
                file.write(f'export {key}={value}\n')

            os.chmod(stub_script, 0o700)

            tcl_path = f'{self.rtl_platform_path}/tcl_files'

            if self.target.get_args().rtl_simulator == 'vsim':

                # Append to the stub script the arguments since they are needed
                # also for vopt which is called by platform scripts
                file.write(f'export VSIM_RUNNER_FLAGS="{" ".join(self.args)}"\n')
                file.write('exec vsim "$@"\n')

                command += [
                    stub_script
                ]

                dpi_cpp_path = args.dpi_cpp_path
                if dpi_cpp_path is None:
                    dpi_cpp_path = os.environ.get('CONFIG_GAPY_DPI_CPP_PATH')

                if dpi_cpp_path is not None:
                    command += [f'-dpicpppath {dpi_cpp_path} -cpppath {dpi_cpp_path}']

                if args.gui:
                    if args.use_default_gui is not True:
                        command += [
                            '-64',
                            f"-do 'source {tcl_path}/config/run_and_exit.tcl'",
                            f"-do 'source {tcl_path}/run.tcl'"
                        ]
                    else:
                        command += [
                            'chip_opt',
                            f'-visualizer={self.rtl_platform_path}/design.bin',
                            '-qwavedb=+signal+msgmode=both+displaymsgmode=both',
                            f"-do 'source {tcl_path}/config/run_and_exit.tcl'",
                            f"-do 'source {tcl_path}/run.tcl'"
                        ]

                    if args.power:
                        command += [
                            f"-do 'source {tcl_path}/run_sim_dump.tcl'"
                        ]
                else:
                    command += [
                        '-64',
                        '-c',
                        f"-do 'source {tcl_path}/config/run_and_exit.tcl'",
                    ]

                    if args.power:
                        command += [
                            f"-do 'source {tcl_path}/run.tcl'",
                            f"-do 'source {tcl_path}/run_sim_dump.tcl'"
                        ]
                    else:
                        command += [
                            f"-do 'source {tcl_path}/run.tcl; run_and_exit'"
                        ]

            elif self.target.get_args().rtl_simulator == 'xcelium':

                file.write('exec xmsim "$@"\n')

                command += [
                    stub_script
                ]

                command += self.args

                command += [
                    'tb', '-64bit', '-licqueue', '-messages', '-xceligen',
                    'seed_only_rand,process_alternate_rng,ignore_worklib_name',
                    '-lps_real_nocorrupt',
                    '-assert_logging_error_off',
                    f'+VSIM_PATH={self.rtl_platform_path}',
                    '+UVM_TESTNAME=SoftTestOnly', '+phy_sel=dphy', '+lane=2lane +data_width=8bit',
                    '+frame_mode=Gen', '-nowarn', 'RNDXCELON', '-sv_lib',
                    f'{args.xcelium_root}/tools/methodology/UVM/CDNS-1.2/'
                        'additions/sv/lib/64bit/libuvmdpi.so',
                    '-INPUT', f'"@source {args.xcelium_root}/tools/methodology/'
                        'UVM/CDNS-1.2/additions/sv/files/tcl/uvm_sim.tcl"',
                    '-runmode'
                ]

                if args.gui:
                    tcl_file = self.target.get_file_path("gapylib/chips/gap/run_gui.tcl")
                    command += [
                        '-gui',
                        '-input', f'{tcl_file}'
                    ]
                else:
                    command += [
                        '-input', f'{tcl_path}/run_and_exit.tcl'
                    ]

            else:
                raise RuntimeError('Unknown RTL simulator: ' + self.target.get_args().rtl_simulator)

        return command


    def __set_env(self, key, value):
        self.env[key] = value


    def __set_arg(self, value):
        self.args.append(value)
