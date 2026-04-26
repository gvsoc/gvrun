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
import inspect
from pathlib import Path
import gvrun.target
import gvrun.commands


def _find_sdk_install_dir() -> Path | None:
    candidates = []

    module_path = Path(__file__).resolve()
    candidates.extend(module_path.parents)

    cwd_path = Path.cwd().resolve()
    candidates.extend(cwd_path.parents)
    candidates.append(cwd_path)

    seen: set[Path] = set()
    ordered_candidates: list[Path] = []
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            ordered_candidates.append(candidate)

    for candidate in ordered_candidates:
        install_dir = candidate / 'install'
        if (install_dir / 'targets').exists() and (install_dir / 'generators').exists():
            return install_dir

    return None

def main(argv: list[str] | None = None) -> int:
    os.environ.setdefault('USE_GVRUN', '1')
    os.environ.setdefault('USE_GVRUN2', '1')

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
    default_platform = os.environ.get('GVRUN_PLATFORM', 'gvsoc')

    parser = argparse.ArgumentParser(description='Execute commands on the target',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter, prog="gvrun")

    _ = parser.add_argument('command', metavar='CMD', type=str, nargs='*',
        help='a command to be executed (execute the command "commands" to get the list of commands)')

    _ = parser.add_argument("--target", '-t', dest="target", default=default_target,
        required=default_target is None, help="specify the target")

    _ = parser.add_argument("--target-dir", dest="target_dirs", default=default_target_dirs, action="append",
        help="append the specified directory to the list of directories where to look for targets")

    _ = parser.add_argument("--parameter", dest="parameters", default=[],
        action="append", help="specify the value of a parameter")

    _ = parser.add_argument("--target-property", dest="target_properties", default=[],
        action="append", help="specify the value of a target property")

    _ = parser.add_argument('--target-opt', dest='target_opt', action="append", default=[],
        help='specify target options')

    _ = parser.add_argument('--config-opt', dest='config_opt', action="append", default=[],
        help='specify target options (backward compatibility)')

    _ = parser.add_argument("--attribute", dest="attributes", default=[],
        action="append", help="specify the value of an attribute")

    _ = parser.add_argument("--flash-content", dest="flash_contents", default=[],
        action="append",
        help="replace a flash's content layout from a JSON file: PATH@FLASHNAME")

    _ = parser.add_argument("--flash-property", dest="flash_properties", default=[],
        action="append",
        help="override a flash property: VALUE@FLASH:SECTION:KEY "
             "(appends for list-typed properties, replaces otherwise)")

    _ = parser.add_argument('--verbose', dest='verbose', type=str, default='critical', choices=[
        'debug', 'info', 'warning', 'error', 'critical'],
        help='Specifies verbose level.')

    _ = parser.add_argument("--no-group", dest="no_group", action="store_true",
        default=False,
        help="For diagram command: show all instances instead of grouping similar components")

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

    _ = parser.add_argument("--rtl-simulator", dest="rtl_simulator",
        default=os.environ.get('GVRUN_RTL_SIMULATOR'),
        type=str,
        help="select the RTL simulator backend (e.g. verilator, vcs); only meaningful with --platform rtl")

    _ = parser.add_argument("--no-config-py", dest="no_config_py",
        action="store_true", default=False,
        help="Do not load config.py from the working directory (useful when "
             "the target is a viewer/utility like utils.fst_dumper)")

    [args, _] = parser.parse_known_args(argv)

    if len(args.target_dirs) == 0:
        install_dir = _find_sdk_install_dir()
        if install_dir is not None:
            args.target_dirs.append(str(install_dir / 'targets'))
            args.target_dirs.append(str(install_dir / 'generators'))

    if len(args.install_dirs) == 0:
        install_dir = _find_sdk_install_dir()
        if install_dir is not None and (install_dir / 'models').exists():
            args.install_dirs.append(str(install_dir / 'models'))

    if len(args.install_dirs) == 0:
        legacy_model_path = os.environ.get('GVRUN_MODEL_PATH')
        if legacy_model_path is not None and legacy_model_path != '':
            args.install_dirs.append(legacy_model_path)

    if args.target is not None and args.target.find('./') == 0:
        args.target = args.target[2:]
        args.target_dirs.append(os.getcwd())

    try:

        logging.basicConfig(level=getattr(logging, args.verbose.upper(), None),
            format='\033[94m[GVRUN]\033[0m %(message)s')

        sys.path = args.target_dirs + sys.path

        selected_target = None
        if args.target is not None:
            target_name = args.target
            from gvrun.target_qualifiers import parse_target_string, apply_target_qualifiers
            parsed = parse_target_string(target_name)
            target_name = parsed.name
            apply_target_qualifiers(parsed, args)

            target_class = gvrun.target.get_target(target_name)
            target_kwargs = {
                "parser": parser,
                "name": "",
            }
            init_signature = inspect.signature(target_class.__init__)
            if "options" in init_signature.parameters:
                target_kwargs["options"] = args.config_opt + args.target_opt

            gvrun.commands.parse_parameter_arg_values(args.parameters)

            gvrun.commands.parse_attribute_arg_values(args.attributes)

            selected_target = target_class(**target_kwargs)

        parser = argparse.ArgumentParser(
            parents=[parser],
            formatter_class=argparse.ArgumentDefaultsHelpFormatter,
            add_help=False,
        )

        args = parser.parse_args(argv)

        if not os.path.isabs(args.work_dir):
            args.work_dir = os.path.join(os.getcwd(), args.work_dir)

        if selected_target is not None:
            gvrun.commands.handle_commands(selected_target, args)

    except RuntimeError as e:
        if args.py_stack:
            raise

        print('Input error: ' + str(e), file = sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
