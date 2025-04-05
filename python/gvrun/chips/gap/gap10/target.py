"""
Provides a common target for all gap chips.
This is mostly used to declare the supported platforms and how to dispatch the commands
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


import argparse
import gapylib.chips.gap.target
import gapylib.chips.gap.gap10.rtl_runner
import gapylib.chips.gap.gap10.properties
import gapylib.chips.gap.gap9_v2.board_runner

class Target(gapylib.chips.gap.target.Target):
    """
    Parent class for all gap targets, which provides all common functions and commands.

    Attributes
    ----------
    parser : argparse.ArgumentParser
        The parser where to add arguments.
    options : List
        A list of options for the target.
    """

    def __init__(self, parser: argparse.ArgumentParser, options: list):
        super().__init__(parser, options)

        # Utility class for managing execution on the board or RTL platform
        self.runner = None


    def handle_command(self, cmd: str):

        args = self.get_args()

        if cmd == 'run':
            self.runner.run()

        elif cmd == 'traces':
            if args.platform == 'rtl':
                self.runner.traces()

        elif cmd == 'image':
            gapylib.target.Target.handle_command(self, cmd)

            # RTL platform needs to generate stim files for flash and efuse
            if args.platform == 'rtl':
                self.runner.image()

        elif cmd == 'flash':
            gapylib.target.Target.handle_command(self, cmd)

        else:
            gapylib.target.Target.handle_command(self, cmd)


    def append_args(self, parser: argparse.ArgumentParser):
        """Append target specific arguments to gapy command-line.

        Parameters
        ----------
        parser : argparse.ArgumentParser
            The parser where to add arguments.
        """

        super().append_args(parser)

        [args, _] = parser.parse_known_args()

        if args.platform == 'rtl':
            self.runner = gapylib.chips.gap.gap10.rtl_runner.Runner(self)

        elif args.platform in ['board', 'fpga']:
            self.runner = gapylib.chips.gap.gap9_v2.board_runner.Runner(self)

        else:
            raise RuntimeError('Unknown platform: ' + args.platform)

        self.runner.append_args(parser)


    def parse_args(self, args: any):
        """Handle arguments.

        Parameters
        ----------
        args :
            The arguments.
        """
        super().parse_args(args)

        gapylib.chips.gap.gap10.properties.declare_properties(self)

        self.runner.parse_args(args)
