# SPDX-FileCopyrightText: 2026 ETH Zurich and University of Bologna and EssilorLuxottica SAS
#
# SPDX-License-Identifier: Apache-2.0
#
# Authors: Germain Haugou (germain.haugou@gmail.com)

"""HostFS flash section — copies files to working directory (not embedded in flash)."""

from __future__ import annotations

import os
import shutil
from gvrun.flash import FlashSection, register_section_template


@register_section_template("hostfs")
class HostfsSection(FlashSection):
    """A host filesystem section.

    Files are copied to the working directory at image generation time,
    not embedded in the flash binary. Useful for development.

    Properties
    ----------
    files : list[str]
        List of file paths to copy to the working directory.
    """

    def __init__(self, name: str, files: list[str] | None = None):
        super().__init__(name)
        self.declare_property('files', list(files or []),
            'List of files to copy to the working directory')

    def build(self):
        if self.parent and self.parent.workdir:
            for file in self.get_property('files'):
                dst = os.path.join(self.parent.workdir, os.path.basename(file))
                shutil.copy(file, dst)

    def is_empty(self) -> bool:
        return len(self.get_property('files')) == 0
