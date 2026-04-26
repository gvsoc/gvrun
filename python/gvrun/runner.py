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


class Runner:
    """Abstract base for a platform-specific runner attached to a Target.

    A Target may register one Runner per platform (gvsoc, verilator, fpga,
    board, ...). When gvrun executes the run/handle_command/generate_all
    flow, the Target's base implementation looks up the runner registered
    for ``args.platform`` and delegates to it. Subclasses override only
    the hooks they need; the rest are no-ops.
    """

    def generate_all(self, path: str) -> None:
        """Produce platform-specific artifacts (boot image, hex file, ...)."""
        _ = path

    def run(self, args: argparse.Namespace) -> int:
        """Launch execution on the platform. Return process exit code."""
        _ = args
        return 0

    def handle_command(self, command: str, args: argparse.Namespace) -> bool:
        """Optional hook for platform-specific commands. Return True if handled."""
        _ = command
        _ = args
        return False
