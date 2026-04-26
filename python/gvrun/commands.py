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

# For python 3.12
from __future__ import annotations
from abc import ABC
import sys
import os.path
import logging
import importlib.util
import shutil
import subprocess
import argparse
import dataclasses
try:
    from typing import override  # Python 3.12+
except ImportError:
    from typing_extensions import override  # Python 3.10–3.11
import gvrun.systree
import gvrun.config
import gvrun.attribute
from gvrun.attribute import set_attributes
from gvrun.parameter import set_parameters, BuildParameter
from gvrun.builder import Builder, CommandInterface
from gvrun.target import Target
from gvrun.systree import SystemTreeNode
from config_tree import Config

commands = [
    ['commands'    , 'Show the list of available commands'],
    ['config'      , 'Show the target configuration'],
    ['targets'     , 'Show the list of available targets'],
    ['image'       , 'Generate the target images needed to run execution'],
    ['flash'       , 'Upload the flash contents to the target'],
    ['flash_layout', 'Dump the layout of all flash memories'],
    ['tree'        , 'Dump the tree of attributes, parameters and parameters'],
    ['run'         , 'Start execution on the target'],
    ['clean'       , 'Remove work directory'],
    ['compile'     , 'Build executables for the target'],
    ['build'       , 'Execute the commands image, flash and compile'],
    ['all'         , 'Execute the commands build and run'],
    ['target_gen'  , 'Generate files required for compiling target'],
    ['diagram'     , 'Generate a Graphviz architecture diagram of the target'],
]

# True if we should generate components
comp_generate = True

def load_config(target: SystemTreeNode|None, args: argparse.Namespace):
    if target is not None:
        _ = BuildParameter(target, 'platform', args.platform, 'Platform providing the target')
        _ = BuildParameter(target, 'builddir', os.path.join(args.work_dir, 'build'), 'Build directory')

        if not getattr(args, 'no_config_py', False) and os.path.exists('config.py'):
            module = import_config('config.py')
            module.declare(target)

        apply_flash_cli_overrides(target, args)

        target.configure_all()

        global _current_target_root
        _current_target_root = target
        check_overrides_consumed()


def _enumerate_top_config_paths(target: SystemTreeNode) -> set[str]:
    """Return paths addressable by ``config(...)`` — the top Config only.

    The "top Config" is the ``config_tree.Config`` attached to the target
    root via ``SystemTreeNode.set_attributes`` (and its nested Configs
    reachable through dataclass fields).

    Paths are reported in the form ``<cfg_path>/<field>`` (the Config's
    own registry path, as used by ``_do_adopt``) plus the root-relative
    alias with the first segment stripped, matching ``_do_adopt``'s
    two-step lookup.
    """
    from dataclasses import fields as dc_fields

    paths: set[str] = set()
    root_cfg = target.get_attributes() if target is not None else None
    if not isinstance(root_cfg, Config):
        return paths

    # Collect the root Config and every nested Config reachable from it.
    visited: set[int] = set()
    stack = [root_cfg]
    configs: list[Config] = []
    while stack:
        cfg = stack.pop()
        if id(cfg) in visited:
            continue
        visited.add(id(cfg))
        configs.append(cfg)
        for f in dc_fields(cfg):
            if hasattr(cfg, f.name):
                val = getattr(cfg, f.name)
                if isinstance(val, Config):
                    stack.append(val)
        stack.extend(c for c in cfg.children if isinstance(c, Config))

    for cfg in configs:
        cfg_path = cfg.path
        for f in dc_fields(cfg):
            if not f.init:
                continue
            full = f'{cfg_path}/{f.name}' if cfg_path else f.name
            paths.add(full)
            if '/' in full:
                paths.add(full.split('/', 1)[1])
    return paths


def check_overrides_consumed():
    """Raise if any ``config(...)``, ``attr(...)`` or ``--attribute`` key
    went unused.

    Called from ``load_config`` after ``target.configure_all()`` — by that
    point every ``Config`` has been instantiated and every
    ``Component``/``Value`` has read its override, so unmatched keys can
    only be typos or paths the target doesn't expose.

    ``config(...)`` is scoped to the **top** Config tree (attached to the
    target root). ``attr(...)`` is scoped to component attributes reached
    via either ``gvrun.systree`` (new Config-backed path) or
    ``gvrun.attribute`` (legacy Tree/Value path).
    """
    target_root = _current_target_root

    # --- config(...) — top Config only -----------------------------------
    if _config_override_keys:
        valid = _enumerate_top_config_paths(target_root)
        unknown = [k for k in _config_override_keys if k not in valid]
        if unknown:
            raise RuntimeError(
                "Unknown config. override(s): "
                + ", ".join(f"'{k}'" for k in unknown)
                + ". config. addresses the top Config tree attached to "
                "the target root; use attr. for per-component "
                "attributes reached via component paths.")

    # --- attr(...) and --attribute — component attributes ----------------
    systree_submitted = gvrun.systree.get_attribute_arg_keys()
    systree_consumed = gvrun.systree.get_consumed_attribute_paths()
    attr_submitted = gvrun.attribute.get_attribute_arg_keys()
    attr_consumed = gvrun.attribute.get_consumed_attribute_paths()

    # A key is considered consumed if either registry picked it up.
    all_submitted = systree_submitted | attr_submitted
    all_consumed = systree_consumed | attr_consumed
    unknown_attr = sorted(all_submitted - all_consumed)
    if unknown_attr:
        top_paths = _enumerate_top_config_paths(target_root)
        hints = [
            f"'{k}' (did you mean config.{k}=...?)" if k in top_paths else f"'{k}'"
            for k in unknown_attr
        ]
        raise RuntimeError(
            "Unknown attr./--attribute override(s): "
            + ", ".join(hints)
            + ". No matching component attribute in the target's tree.")


# Set by load_config so check_overrides_consumed can walk the systree.
_current_target_root: SystemTreeNode | None = None


def apply_flash_cli_overrides(target: SystemTreeNode, args: argparse.Namespace):
    """Apply ``--flash-content`` and ``--flash-property`` CLI overrides.

    Called from :func:`load_config` after ``config.py`` has declared flashes
    and any imperative content, so CLI overrides win.
    """
    flash_contents = getattr(args, 'flash_contents', None) or []
    flash_properties = getattr(args, 'flash_properties', None) or []

    for arg in flash_contents:
        if '@' not in arg:
            raise RuntimeError(
                f'Invalid --flash-content argument "{arg}": expected PATH@FLASHNAME')
        path, flash_name = arg.rsplit('@', 1)
        target.get_flash(flash_name).set_content(path)

    for arg in flash_properties:
        if '@' not in arg:
            raise RuntimeError(
                f'Invalid --flash-property argument "{arg}": '
                f'expected VALUE@FLASH:SECTION:KEY')
        value, locator = arg.rsplit('@', 1)
        parts = locator.split(':')
        if len(parts) != 3:
            raise RuntimeError(
                f'Invalid --flash-property argument "{arg}": '
                f'locator "{locator}" must have form FLASH:SECTION:KEY')
        flash_name, section_name, key = parts
        target.get_flash(flash_name).set_property(section_name, key, value)

    # Materialise sections so ``after_parse`` side effects (e.g. registering
    # an app_binary ELF as an executable) happen before ``generate_all``.
    for flash in target.get_flashes().values():
        flash.parse_content()


def dump_tree(target: Target, args: argparse.Namespace):

    options = set(args.tree_format.split(':'))

    target.process_and_dump_tree(
        len({'all', 'attr'} & options) > 0,
        len({'all', 'build'} & options) > 0,
        len({'all', 'target'} & options) > 0,
        len({'all', 'attr'} & options) > 0,
        len({'all', 'prop'} & options) > 0
    )


def compile(target: Target, args: argparse.Namespace):
    builder = Builder(args.jobs, args.verbose)
    try:
        target.compile_all(builder, os.path.join(args.work_dir, 'build'))
    except:
        builder.stop()
        raise

    retval = builder.wait_completion()
    builder.stop()

    if retval != 0:
        raise RuntimeError(f'Compilation returned an error (exitcode: {retval})')

def generate_diagram_cmd(target: Target, args: argparse.Namespace):
    from gvrun.diagram import generate_diagram

    # Get the top-level GVSOC component from the target
    top = target.get_systree()

    # The actual component tree is inside the gvsoc Component hierarchy
    # We need to find it — it's typically the component that has bindings/components
    gvsoc_comp = _find_gvsoc_component(top)
    if gvsoc_comp is None:
        print("Error: could not find the GVSoC component tree in the target")
        return

    output = getattr(args, 'diagram_output', None) or 'architecture.dot'
    target_name = getattr(args, 'target', None) or 'GVSoC Target'
    group_similar = not getattr(args, 'no_group', False)

    generate_diagram(gvsoc_comp, output, target_name=target_name, group_similar=group_similar)


def _find_gvsoc_component(node):
    """Walk the SystemTreeNode hierarchy to find the gvsoc Component subtree."""
    # Check if this node itself is a gvsoc Component with components dict
    if hasattr(node, 'components') and isinstance(getattr(node, 'components'), dict) and \
            len(node.components) > 0:
        return node

    # Check children (SystemTreeNode uses _get_childs)
    childs = []
    if hasattr(node, '_get_childs'):
        childs = node._get_childs()
    elif hasattr(node, 'components'):
        childs = list(node.components.values())

    for child in childs:
        result = _find_gvsoc_component(child)
        if result is not None:
            return result

    return None


_flash_images_generated = False

def generate_flash_images(target: Target, args: argparse.Namespace):
    """Generate flash images for all non-empty registered flashes."""
    global _flash_images_generated
    if _flash_images_generated:
        return
    _flash_images_generated = True

    systree = target.get_systree() or target
    flashes = systree.get_flashes()
    workdir = os.path.join(args.work_dir, 'build')
    for flash in flashes.values():
        if not flash.is_empty():
            flash.generate_image(workdir)


def __print_available_commands():
    print('Available commands:')

    for command in commands:
        print(f'  {command[0]:16s} {command[1]}')

def handle_command(target: Target, command: str, args: argparse.Namespace):
    global comp_generate

    if target.handle_command(command, args):
        return

    if command == 'commands':
        __print_available_commands()
        return

    if command == 'config':
        target.config.dump()
        return

    if command == 'clean':
        shutil.rmtree(os.path.join(args.work_dir, 'build'), ignore_errors=True)
        return

    if command == 'tree':
        dump_tree(target, args)
        return

    if command in ['compile', 'all', 'build']:
        compile(target, args)
        if command == 'compile':
            return

    if command in ['image', 'all', 'build']:
        if comp_generate:
            comp_generate = False
            target.generate_all(os.path.join(args.work_dir, 'build'))
        generate_flash_images(target, args)
        if command == 'image':
            return

    if command in ['run', 'all']:
        if comp_generate:
            comp_generate = False
            target.generate_all(os.path.join(args.work_dir, 'build'))
        generate_flash_images(target, args)
        _ = target.run(args)
        if command == 'run':
            return

    if command in ['components', 'flash']:
        _ = target.handle_command(command, args)

    if command == 'flash_layout':
        systree = target.get_systree() or target
        for flash in systree.get_flashes().values():
            level = getattr(args, 'flash_layout_level', 0) or 0
            flash.dump_layout(level)

    if command == 'target_gen':
        target.target_gen_walk(os.path.join(args.work_dir, 'build'))

    if command == 'diagram':
        generate_diagram_cmd(target, args)

def parse_parameter_arg_values(parameters: list[str]):
    set_parameters(parameters)


# Config-field overrides submitted via ``config(...)`` qualifier; recorded
# here so we can detect keys that never matched a Config field after the
# target is constructed.
_config_override_keys: list[str] = []


def track_config_overrides(values: list[str]):
    """Record config(...) keys for the post-construction consumption check."""
    for prop in values:
        key, _ = prop.split('=', 1)
        _config_override_keys.append(key)


def parse_attribute_arg_values(attributes: list[str]):
    """Override component attributes only.

    Same scope as ``attr(...)`` target qualifier — feeds both:

    - ``gvrun.systree`` (picked up by ``Component.__init__`` for
      Config-backed component properties).
    - ``gvrun.attribute`` (picked up by ``Value.__init__`` for legacy
      Tree/Value hierarchies).

    Unmatched paths are reported by :func:`check_overrides_consumed`.
    """
    gvrun.systree.set_attributes(attributes)
    set_attributes(attributes)

def handle_commands(target: Target, args: argparse.Namespace):

    commands = args.command

    target._set_active_args(args)

    load_config(target.get_systree(), args)

    for command in commands:
        handle_command(target, command, args)


class Command(CommandInterface,ABC):
    """
    Parent class for all commands, which provides functionalities for enqueueing commands to be
    executed.

    Attributes
    ----------
    builder : Builder
        Builder which will execute commands
    """

    def __init__(self, builder: "Builder"):
        self.trigger_count: int = 0
        self.trigger_commands: list[Command] = []
        self.builder: Builder = builder

    def has_trigger(self):
        return len(self.trigger_commands) != 0

    def add_trigger(self, command: Command):
        command.trigger_count += 1
        self.trigger_commands.append(command)

    def command_done(self):
        if self.retval == 0:
            for command in self.trigger_commands:
                command.trigger_count -= 1
                if command.trigger_count == 0:
                    self.builder.push_command(command)

    def execute(self, cmd: str, path: str|None=None):
        if self.builder.verbose == 'debug':
            print (cmd, flush=True)

        proc = subprocess.run(cmd.split(), cwd=path, text=True, capture_output=True)
        _ = sys.stdout.write(proc.stdout)
        _ = sys.stderr.write(proc.stderr)
        self.retval: int = proc.returncode
        self.command_done()
        self.builder.command_done(self)

    @override
    def get_retval(self) -> int:
        return self.retval


def get_abspath(args: argparse.Namespace, relpath: str) -> str:
        """Return the absolute path depending on the working directory.

        If no working directory was specified, the relpath is appended to the current directory.
        Otherwise it is appended to the working directory.

        Parameters
        ----------
        relpath : str
            Relative path of the file.

        Returns
        -------
        str
            The absolute path.
        """
        if os.path.isabs(relpath):
            return relpath

        if args.work_dir is None:
            return os.path.abspath(relpath)

        return os.path.join(args.work_dir, relpath)

def add_subdirectory(name: str, target: Target):
    module = import_config(os.path.join(name, 'config.py'))
    module.declare(target)


def import_config(name: str):

    logging.debug(f'Importing config (name: {name})')

    if not os.path.isabs(name):
        name = os.path.join(os.getcwd(), name)

    try:
        spec = importlib.util.spec_from_file_location(name, name)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Unable to load spec for {name}")
        module = importlib.util.module_from_spec(spec)
        sys.modules["module.name"] = module
        spec.loader.exec_module(module)

    except FileNotFoundError:
        raise RuntimeError('Unable to open test configuration file: ' + name)

    return module
