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
import psutil
import queue

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
            self.nb_threads = psutil.cpu_count(logical=True) or nb_threads
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
