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

import sys
import os.path
import logging
import importlib.util
import rich.tree
import threading
import psutil
import queue
import shutil

user_properties = {}
target_properties = {}
configured_after_compile = False

commands = [
    ['commands'    , 'Show the list of available commands'],
    ['targets'     , 'Show the list of available targets'],
    ['image'       , 'Generate the target images needed to run execution'],
    ['flash'       , 'Upload the flash contents to the target'],
    ['flash_layout', 'Dump the layout of the flashes'],
    ['flash_dump_sections', 'Dump each section of each flash memory'],
    ['flash_dump_app_sections', 'Dump each section of each flash memory'],
    ['flash_properties', 'Dump the value of all flash section properties'],
    ['target_properties', 'Dump the value of all target properties'],
    ['run',         'Start execution on the target'],
    ['clean',       'Remove work directory'],
    ['compile',     'Build executables for the target'],
    ['properties',  'Dump build properties'],
]

def get_user_property(name):
    return user_properties.get(name)

def get_target_property(name):
    return target_properties.get(name)

def import_config(name):

    logging.debug(f'Importing config (name: {name})')

    if not os.path.isabs(name):
        name = os.path.join(os.getcwd(), name)

    try:
        spec = importlib.util.spec_from_file_location(name, name)
        module = importlib.util.module_from_spec(spec)
        sys.modules["module.name"] = module
        spec.loader.exec_module(module)

    except FileNotFoundError as exc:
        raise RuntimeError('Unable to open test configuration file: ' + name)

    return module

def load_config(target, args):
    global user_properties

    for prop_array in args.properties:
        for prop in prop_array.split(','):
            key, value = prop.split('=', 1)
            if user_properties.get(key) is not None:
                if isinstance(user_properties.get(key), list):
                    user_properties[key].append(value)
                else:
                    user_properties[key] = [user_properties.get(key), value]
            else:
                user_properties[key] = value

    target.declare_property('platform', args.platform, 'Platform providing the target')
    target.declare_property('builddir', args.build_dir, 'Build directory')

    module = import_config('config.py')
    module.declare(target)

    target.configure_all()


def dump_properties(target):
    tree = rich.tree.Tree('Properties')
    target.dump_build_properties(tree)
    rich.print(tree)

def compile(target, args):
    builder = Builder(args.jobs, args.verbose)
    target.model.build(builder, args.build_dir)
    retval = builder.wait_completion()
    builder.stop()

    if retval != 0:
        raise RuntimeError(f'Compilation returned an error (exitcode: {retval})')

def handle_command(target, command, args):

    global configured_after_compile

    if command == 'target_prepare':
        target.model.target_prepare_walk()
        return

    if command == 'target_gen':
        target.model.target_gen_walk()
        return

    if command == 'clean':
        shutil.rmtree(args.build_dir, ignore_errors=True)
        return

    if command == 'properties':
        dump_properties(target)
        return

    if command == 'target_properties':
        target.dump_target_properties()
        return

    if command in ['compile', 'all', 'build']:
        compile(target, args)
        if command == 'compile':
            return

    if not configured_after_compile:
        configured_after_compile = True
        target.configure_after_compile_all()

    if command == 'flash_layout':
        target.dump_flash_layout_walk(args.layout_level)
        return

    if command in ['image', 'all', 'build']:
        target.model.generate_all(args.build_dir)
        if command == 'image':
            return

    if command in ['run', 'all']:
        target.model.generate_all(args.build_dir)
        target.run(args)
        if command == 'run':
            return

    if command in ['components', 'flash']:
        target.handle_command(command, args)


def parse_target_properties(args):
    global target_properties

    for prop in args.target_properties:
        key, value = prop.split('=', 1)
        target_properties[key] = value


def handle_commands(target, args):

    commands = args.command

    if 'properties' in commands or 'compile' in commands or 'all' in commands or 'build' in commands:
        load_config(target.model, args)

    for command in commands:
        handle_command(target, command, args)


class CommandCommon():

    def __init__(self, builder):
        self.trigger_count = 0
        self.trigger_commands = []
        self.builder = builder

    def has_trigger(self):
        return len(self.trigger_commands) != 0

    def add_trigger(self, command):
        command.trigger_count += 1
        self.trigger_commands.append(command)

    def command_done(self):
        for command in self.trigger_commands:
            command.trigger_count -= 1
            if command.trigger_count == 0:
                self.builder.push_command(command)

class Builder():

    class BuilderWorker(threading.Thread):

        def __init__(self, builder):
            super().__init__()

            self.builder = builder

        def run(self):
            while True:
                test = self.builder.pop_command()
                if test is None:
                    return
                test.run()

    def __init__(self, nb_threads, verbose):
        if nb_threads == -1:
            self.nb_threads = psutil.cpu_count(logical=True)
        else:
            self.nb_threads = nb_threads

        self.nb_commands_failed = 0
        self.nb_pending_commands = 0
        self.lock = threading.Lock()
        self.condition = threading.Condition(self.lock)
        self.verbose = verbose
        self.threads = []
        self.queue = queue.Queue()

        for thread_id in range(0, self.nb_threads):
            thread = Builder.BuilderWorker(self)
            self.threads.append(thread)
            thread.start()

    def stop(self):
        for thread in self.threads:
            self.queue.put(None)
        for thread in self.threads:
            thread.join()


    def push_command(self, command):
        self.lock.acquire()
        self.nb_pending_commands += 1
        self.queue.put(command)
        self.lock.release()

    def pop_command(self):
        return self.queue.get()

    def command_done(self, command):
        self.lock.acquire()
        if command.retval != 0:
            self.nb_commands_failed += 1
        self.nb_pending_commands -= 1

        self.condition.notify_all()
        self.lock.release()

    def wait_completion(self):
        self.lock.acquire()
        while self.nb_pending_commands > 0:
            self.condition.wait()

            if self.nb_commands_failed > 0:
                while not self.queue.empty():
                    self.queue.get()
                self.nb_pending_commands = 0

        self.lock.release()
        return self.nb_commands_failed


def get_abspath(args, relpath: str) -> str:
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

        if args.build_dir is None:
            return os.path.abspath(relpath)

        return os.path.join(args.build_dir, relpath)

def add_subdirectory(name, target):
    module = import_config(os.path.join(name, 'config.py'))
    module.declare(target)


def import_config(name):

    logging.debug(f'Importing config (name: {name})')

    if not os.path.isabs(name):
        name = os.path.join(os.getcwd(), name)

    try:
        spec = importlib.util.spec_from_file_location(name, name)
        module = importlib.util.module_from_spec(spec)
        sys.modules["module.name"] = module
        spec.loader.exec_module(module)

    except FileNotFoundError as exc:
        raise RuntimeError('Unable to open test configuration file: ' + name)

    return module
