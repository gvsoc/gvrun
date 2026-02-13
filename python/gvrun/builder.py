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

import threading
from typing import override
import psutil
import queue
from abc import ABC, abstractmethod

class CommandInterface(ABC):

    @abstractmethod
    def get_retval(self) -> int:
        pass

    @abstractmethod
    def run(self) -> None:
        pass

class Builder():

    class BuilderWorker(threading.Thread):

        def __init__(self, builder: Builder):
            super().__init__()

            self.builder: Builder = builder

        @override
        def run(self):
            while True:
                test: CommandInterface|None = self.builder.pop_command()
                if test is None:
                    return
                test.run()

    def __init__(self, nb_threads: int, verbose: str):
        self.nb_threads: int
        if nb_threads == -1:
            self.nb_threads = psutil.cpu_count(logical=True) or nb_threads
        else:
            self.nb_threads = nb_threads

        self.nb_commands_failed: int = 0
        self.nb_pending_commands: int = 0
        self.lock: threading.Lock = threading.Lock()
        self.condition: threading.Condition = threading.Condition(self.lock)
        self.verbose: str = verbose
        self.threads: list[threading.Thread] = []
        self.queue: queue.Queue[CommandInterface|None] = queue.Queue()

        for _ in range(0, self.nb_threads):
            thread = Builder.BuilderWorker(self)
            self.threads.append(thread)
            thread.start()

    def stop(self):
        for thread in self.threads:
            self.queue.put(None)
        for thread in self.threads:
            thread.join()


    def push_command(self, command: CommandInterface):
        _ = self.lock.acquire()
        self.nb_pending_commands += 1
        self.queue.put(command)
        self.lock.release()

    def pop_command(self) -> CommandInterface|None:
        return self.queue.get()

    def command_done(self, command: CommandInterface):
        _ = self.lock.acquire()
        if command.get_retval() != 0:
            self.nb_commands_failed += 1
        self.nb_pending_commands -= 1

        self.condition.notify_all()
        self.lock.release()

    def wait_completion(self):
        _ = self.lock.acquire()
        while self.nb_pending_commands > 0:
            _ = self.condition.wait()

            if self.nb_commands_failed > 0:
                while not self.queue.empty():
                    _ = self.queue.get()
                self.nb_pending_commands = 0

        self.lock.release()
        return self.nb_commands_failed
