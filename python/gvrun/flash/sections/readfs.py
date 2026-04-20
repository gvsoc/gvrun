# SPDX-FileCopyrightText: 2026 ETH Zurich and University of Bologna and EssilorLuxottica SAS
#
# SPDX-License-Identifier: Apache-2.0
#
# Authors: Germain Haugou (germain.haugou@gmail.com)

"""ReadFS flash section — read-only filesystem with file index."""

from __future__ import annotations

import os.path
from gvrun.flash import FlashSection, register_section_template
from gvrun.utils import CStruct, CStructParent


@register_section_template("readfs")
class ReadfsSection(FlashSection):
    """A read-only filesystem section.

    Packs files with a header index for random access by name.

    Properties
    ----------
    files : list[str]
        List of file paths to include. Supports ``host_path:target_name`` syntax.
    dirs : list[str]
        List of directories whose contents are included.
    """

    def __init__(self, name: str, files: list[str] | None = None,
                 dirs: list[str] | None = None):
        super().__init__(name)
        self.declare_property('files', list(files or []),
            'List of files to include (supports host_path:target_name)')
        self.declare_property('dirs', list(dirs or []),
            'List of directories whose contents are included')

    def build(self):
        # Resolve file paths -> (target_name, host_path) pairs
        file_entries: list[tuple[str, str]] = []

        for file in self.get_property('files'):
            if ':' in file:
                host_path, target_path = file.split(':', 1)
                file_entries.append((os.path.join(target_path, os.path.basename(host_path)),
                                     host_path))
            else:
                file_entries.append((os.path.basename(file), file))

        for directory in self.get_property('dirs'):
            target_dir = None
            if ':' in directory:
                directory, target_dir = directory.split(':', 1)
            for fname in os.listdir(directory):
                fpath = os.path.join(directory, fname)
                if os.path.isfile(fpath):
                    tname = os.path.join(target_dir, fname) if target_dir else fname
                    file_entries.append((tname, fpath))

        # Build binary structures
        top = CStructParent('readfs', parent=self)

        # Main header: fs_size (8B) + nb_files (4B)
        header = CStruct('header', top)
        header.add_field('fs_size', 'Q')
        header.add_field('nb_files', 'I')

        # Per-file headers: offset (4B) + file_size (4B) + name_len (4B) + name (variable)
        file_headers = []
        for target_name, _ in file_entries:
            fh = CStruct(f'{target_name}_header', top)
            fh.add_field('offset', 'I')
            fh.add_field('file_size', 'I')
            fh.add_field('name_len', 'I')
            fh.add_field_array('name', len(target_name) + 1)
            file_headers.append(fh)

        # File contents
        file_structs = []
        for target_name, host_path in file_entries:
            fs = CStruct(f'{target_name}_data', top)
            fs.add_field_array('data', os.path.getsize(host_path))
            file_structs.append(fs)

        # Fill in header values
        header_size = header.get_size()
        for fh in file_headers:
            header_size += fh.get_size()

        header.set_field('fs_size', header_size)
        header.set_field('nb_files', len(file_entries))

        for i, (target_name, host_path) in enumerate(file_entries):
            fh = file_headers[i]
            fs = file_structs[i]

            fh.set_field('offset', fs.get_offset() - self.get_offset())
            fh.set_field('file_size', os.path.getsize(host_path))
            fh.set_field('name_len', len(target_name) + 1)
            fh.set_field('name', target_name.encode('utf-8') + b'\x00')

            with open(host_path, 'rb') as f:
                fs.set_field('data', f.read())

    def is_empty(self) -> bool:
        return (len(self.get_property('files')) == 0
                and len(self.get_property('dirs')) == 0)

    def get_partition_type(self) -> int:
        return 0x1

    def get_partition_subtype(self) -> int:
        return 0x81
