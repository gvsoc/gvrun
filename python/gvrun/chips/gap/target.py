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
import gapylib.target
import gapylib.chips.gap.properties

class Target(gapylib.target.Target):
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

    def parse_args(self, args: any):
        super().parse_args(args)

        gapylib.chips.gap.properties.declare_properties(self)

    def handle_command(self, cmd: str) -> int:

        if cmd == 'run':
            # To be implemented for board and rtl, gvsoc is using another board generator
            return -1

        return gapylib.target.Target.handle_command(self, cmd)
