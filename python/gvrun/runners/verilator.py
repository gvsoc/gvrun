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

from __future__ import annotations

import argparse
import os
import subprocess
from gvrun.runner import Runner


class VerilatorRunner(Runner):
    """Run a PulpOS executable on a Verilator-built RTL simulator.

    The runner converts each ELF produced by ``gvrun compile`` into a Verilog
    hex (via objcopy) during ``generate_all`` and launches the simulator
    binary with ``+firmware=<hex>`` during ``run``. Extra runner flags
    registered via ``Target.add_runner_flags`` are appended to the simulator
    command line.
    """

    def __init__(self,
                 target,
                 simulator: str,
                 objcopy: str | None = None,
                 firmware_arg: str = '+firmware',
                 extra_args: list[str] | None = None,
                 gui: bool = False,
                 trace_path: str | None = None,
                 viewer: str = 'gvwave'):
        super().__init__()
        self.target = target
        self.simulator = simulator
        self.objcopy = objcopy or os.environ.get(
            'RISCV32_GCC_TOOLCHAIN', '') + '/bin/riscv32-unknown-elf-objcopy'
        self.firmware_arg = firmware_arg
        self.extra_args = list(extra_args) if extra_args else []
        self.gui = gui
        self.trace_path = trace_path
        self.viewer = viewer
        self.__firmwares: list[str] = []

    def _hex_path(self, elf_path: str) -> str:
        return elf_path + '.hex'

    def _collect_executables(self):
        """Collect executables attached anywhere on the target (target itself
        plus the system tree returned by get_systree, which is the model root
        for GVSoC targets)."""
        seen = set()
        result = []
        nodes = [self.target]
        systree = None
        getter = getattr(self.target, 'get_systree', None)
        if callable(getter):
            systree = getter()
            if systree is not None:
                nodes.append(systree)
        for node in nodes:
            for exe in node.get_executables():
                if id(exe) in seen:
                    continue
                seen.add(id(exe))
                result.append(exe)
        return result

    def generate_all(self, path: str) -> None:
        _ = path
        self.__firmwares = []
        for exe in self._collect_executables():
            elf = exe.get_binary()
            if elf is None or not os.path.exists(elf):
                continue
            hex_path = self._hex_path(elf)
            cmd = [self.objcopy, '-O', 'verilog', elf, hex_path]
            proc = subprocess.run(cmd, text=True, capture_output=True)
            if proc.returncode != 0:
                raise RuntimeError(
                    f'objcopy failed (cmd: {" ".join(cmd)}):\n{proc.stderr}')
            self.__firmwares.append(hex_path)

    def run(self, args: argparse.Namespace) -> int:
        if not self.simulator:
            raise RuntimeError(
                'VerilatorRunner: no simulator binary configured (set via '
                'target option verilator.simulator or env)')
        if not os.path.exists(self.simulator):
            raise RuntimeError(
                f'VerilatorRunner: simulator binary not found: {self.simulator}')
        if not self.__firmwares:
            raise RuntimeError(
                'VerilatorRunner: no firmware was produced (run generate_all '
                'or compile first)')

        cmd = [self.simulator]
        for fw in self.__firmwares:
            cmd.append(f'{self.firmware_arg}={fw}')
        cmd += self.extra_args
        cmd += self.target.get_runner_flags()

        # GUI mode: force tracing to a known path so we can hand it to the
        # viewer once the sim is done. Don't override an explicit +trace= the
        # caller already provided.
        trace_path = None
        if self.gui:
            already_set = any(a.startswith('+trace') for a in cmd)
            if not already_set:
                trace_path = self.trace_path or os.path.join(
                    getattr(args, 'work_dir', None) or os.getcwd(), 'sim.fst')
                cmd.append(f'+trace={trace_path}')

        if getattr(args, 'verbose', None) == 'debug':
            print(' '.join(cmd), flush=True)

        proc = subprocess.run(cmd)
        if proc.returncode != 0:
            return proc.returncode

        if self.gui and trace_path is not None:
            if not os.path.exists(trace_path):
                raise RuntimeError(
                    f'VerilatorRunner: --gui requested but trace file was not '
                    f'produced at {trace_path}')
            print(f'[gvrun] opening trace in {self.viewer}: {trace_path}',
                  flush=True)
            view = subprocess.run([self.viewer, trace_path])
            return view.returncode

        return 0
