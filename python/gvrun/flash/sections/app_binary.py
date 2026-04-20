# SPDX-FileCopyrightText: 2026 ETH Zurich and University of Bologna and EssilorLuxottica SAS
#
# SPDX-License-Identifier: Apache-2.0
#
# Authors: Germain Haugou (germain.haugou@gmail.com)

"""AppBinary flash section — carries a pre-built ELF binary."""

from __future__ import annotations

import os
from gvrun.flash import FlashSection, register_section_template
from gvrun.systree import ExecutableContainer
from gvrun.utils import CStruct, CStructParent


@register_section_template("app_binary")
class AppBinarySection(FlashSection):
    """A section holding a pre-built ELF application binary.

    Typically used when a Make-based build produces the ELF externally and
    points gvrun at it via ``--flash-property PATH@FLASH:app_binary:binary``.

    Properties
    ----------
    binary : str
        Path to the ELF (or raw binary) to embed.
    boot : bool
        If True, this section is marked as the boot image.
    """

    def __init__(self, name: str, binary: str | None = None, boot: bool = False):
        super().__init__(name)
        self.declare_property('binary', binary or '',
            'Path to the ELF or raw binary to embed')
        self.declare_property('boot', bool(boot),
            'Whether this section is the boot image')
        self._announced_binary: str | None = None

    def _announce_binary(self):
        """Register the ELF as an executable on the flash's owning node.

        This makes the binary visible to any ISS / loader that has subscribed
        via ``register_binary_handler``. Idempotent for a given path.
        """
        binary_path = self.get_property('binary')
        if not binary_path or binary_path == self._announced_binary:
            return
        owner = getattr(self.parent, 'owner', None) if self.parent else None
        if owner is None:
            return
        owner.add_executable(ExecutableContainer(binary_path))
        self._announced_binary = binary_path

    def after_parse(self):
        self._announce_binary()

    def build(self):
        self._announce_binary()

        # Only embed the ELF into the flash image when ``boot`` is True —
        # otherwise this section just signals the simulator which binary the
        # ISS should load. Platforms that boot from flash (like the full GAP9
        # ROM path) set boot=True; simulation platforms that use an ELF
        # loader keep it False.
        if not self.get_property('boot'):
            return

        binary_path = self.get_property('binary')
        if not binary_path:
            return

        with open(binary_path, 'rb') as f:
            data = f.read()

        top = CStructParent('app_binary', parent=self)
        block = CStruct('data', top)
        block.add_field_array('data', len(data))
        block.set_field('data', data)

    def is_empty(self) -> bool:
        if not self.get_property('boot'):
            return True
        binary = self.get_property('binary')
        return not binary or not os.path.exists(binary)

    def get_partition_type(self) -> int:
        return 0x0

    def get_partition_subtype(self) -> int:
        return 0x71
