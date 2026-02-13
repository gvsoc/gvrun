#!/usr/bin/env python3

#
# Copyright (C) 2025 Germain Haugou
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
# Authors: Germain Haugou (germain.haugou@gmail.com)
#

import os
import argparse
import logging
import sys
import gvrun.target
import gvrun.commands

default_target = os.environ.get('GVRUN_TARGET')
default_target_dirs = os.environ.get('GVRUN_TARGET_DIRS')
if default_target_dirs is None:
    default_target_dirs = []
else:
    default_target_dirs = default_target_dirs.split(':')
default_model_dirs = os.environ.get('GVRUN_MODEL_DIRS')
if default_model_dirs is None:
    default_model_dirs = []
else:
    default_model_dirs = default_model_dirs.split(':')
default_platform = os.environ.get('GVRUN_PLATFORM')

# Generic gapy options, all for specifying the target and its options
parser = argparse.ArgumentParser(description='Execute commands on the target',
    formatter_class=argparse.ArgumentDefaultsHelpFormatter, prog="gvrun", add_help=False)

_ = parser.add_argument('command', metavar='CMD', type=str, nargs='*',
    help='a command to be executed (execute the command "commands" to get the list of commands)')

_ = parser.add_argument("--target", '-t', dest="target", default=default_target,
	required=default_target is None, help="specify the target")

_ = parser.add_argument("--target-dir", dest="target_dirs", default=default_target_dirs, action="append",
    help="append the specified directory to the list of directories where to look for targets")

_ = parser.add_argument("--parameter", dest="parameters", default=[],
    action="append", help="specify the value of a parameter")

_ = parser.add_argument("--attribute", dest="attributes", default=[],
    action="append", help="specify the value of an attribute")

_ = parser.add_argument('--verbose', dest='verbose', type=str, default='critical', choices=[
    'debug', 'info', 'warning', 'error', 'critical'],
    help='Specifies verbose level.')

_ = parser.add_argument('--tree-format', dest='tree_format', default='arch:target:build',
    help=(
        "Specify tree format as a list of items separated by ':'.\n"
        "Available items:\n"
        "  attr   - Show attributes (architecture high-level characteristics).\n"
        "  arch   - Show architecture parameters (low-level model parameters).\n"
        "  target - Show target parameters (parameters for configuring execution on targets).\n"
        "  build  - Show build parameters (parameters for building target executables).\n"
        "  prop   - Show target properties (low-level model characteristics).\n"
        "  all    - Show everything.\n"
        "\n"
    ))

_ = parser.add_argument('--py-stack', dest='py_stack', action="store_true",
    help='Show python exception stack.')

_ = parser.add_argument("--model-dir", dest="install_dirs", action="append", default=default_model_dirs,
    type=str, help="specify an installation path where to find models (only for GVSOC)")

_ = parser.add_argument('--work-dir',  dest='work_dir', default=os.getcwd(),
    help='Specify working directory (from where simulation is launched).')

_ = parser.add_argument("--jobs", "-j", dest="jobs", default=-1, type=int,
    help="Specify the number of worker threads")

_ = parser.add_argument("--platform", dest="platform", default=default_platform,
    required=default_platform is None,
    choices=['fpga', 'board', 'rtl', 'gvsoc'],
    type=str, help="specify the platform used for the target")

# Do a first argument parse so that we can get the target and add more arguments, depending on
# the target
[args, otherArgs] = parser.parse_known_args()

if args.target.find('./') == 0:
    args.target = args.target[2:]
    args.target_dirs.append(os.getcwd())

try:

    logging.basicConfig(level=getattr(logging, args.verbose.upper(), None),
        format='\033[94m[GVRUN]\033[0m %(message)s')

    # Targets will be imported as python modules so the specified target directories must be
    # appended to the python path
    sys.path = args.target_dirs + sys.path

    # Instantiate the specified target or if no target is specified, instantiate an empty one
    # since we need a target to handle commands
    selected_target = None
    if args.target is not None:
        # Check if the target name has parameters inlined and if so, inject them
        # into the list of parameters
        target_name = args.target
        parameters = []
        if target_name.find(':') != -1:
            target_name, parameters = target_name.split(':')
            for property_desc in parameters.split(','):
                args.parameters.append(property_desc)

        gvrun.commands.parse_parameter_arg_values(args.parameters)

        gvrun.commands.parse_attribute_arg_values(args.attributes)

        target_class = gvrun.target.get_target(target_name)
        selected_target = target_class(
            parser=parser, name=''
        )

    parser = argparse.ArgumentParser(
        parents=[parser],
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    args = parser.parse_args()

    if not os.path.isabs(args.work_dir):
        args.work_dir = os.path.join(os.getcwd(), args.work_dir)

    if selected_target is not None:
        gvrun.commands.handle_commands(selected_target, args)

except RuntimeError as e:
    if args.py_stack:
        raise

    print('Input error: ' + str(e), file = sys.stderr)
    sys.exit(1)
