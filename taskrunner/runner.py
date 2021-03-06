from importlib import import_module
from importlib.machinery import SourceFileLoader
from itertools import chain

from .config import Config, RawConfig
from .task import Task
from .util import get_hr, print_debug, print_header, print_info, print_warning


class TaskRunner:

    def __init__(self, config_file=None, env=None, tasks_module='tasks.py', default_echo=False,
                 default_hide=None, debug=False):
        self.config_file = config_file
        self.env = env
        self.tasks_module = tasks_module
        self.default_echo = default_echo
        self.default_hide = default_hide
        self.debug = debug

    def run(self, args):
        all_tasks = self.load_tasks(self.tasks_module)
        tasks_to_run = self.get_tasks_to_run(all_tasks, args)
        configs = {}

        for task, task_args in tasks_to_run:
            self.print_debug('Task to run:', task.name, task_args)

        for task, task_args in tasks_to_run:
            task_env = self.env or task.default_env
            if task_env not in configs:
                configs[task_env] = self.load_config(task_env)
            task_config = configs[task_env]
            task.run(task_config, task_args)

    def load_config(self, env=None):
        config = Config(
            config_file=self.config_file,
            env=env or self.env,
            run=RawConfig(echo=self.default_echo, hide=self.default_hide),
            debug=self.debug,
        )
        return config

    def load_tasks(self, tasks_module):
        if tasks_module.endswith('.py'):
            module_loader = SourceFileLoader('tasks', tasks_module)
            module = module_loader.load_module()
        else:
            module = import_module(tasks_module)
        objects = vars(module).values()
        tasks = {obj.name: obj for obj in objects if isinstance(obj, Task)}
        return tasks

    def get_tasks_to_run(self, all_tasks, args):
        tasks = []
        while args:
            task_and_args = self.partition_args(all_tasks, args)
            tasks.append(task_and_args)
            task_args = task_and_args[1]
            num_consumed = len(task_args) + 1
            args = args[num_consumed:]
        return tasks

    def partition_args(self, all_tasks, args):
        name = args[0]

        try:
            task = all_tasks[name]
        except KeyError:
            raise TaskRunnerError('Unknown task: {name}'.format(name=name)) from None

        args = args[1:]
        task_args = []
        partition = [task, task_args]

        prev_args = chain([None], args[:-1])
        next_args = chain(args[1:], [None])

        for prev_arg, arg, next_arg in zip(prev_args, args, next_args):
            if arg in all_tasks:
                option = task.arg_map.get(prev_arg)
                if option is None or option.is_bool:
                    break
            if arg.startswith(':') and arg != ':':
                arg = arg[1:]
            task_args.append(arg)

        return partition

    def print_debug(self, *args, **kwargs):
        if self.debug:
            print_debug(*args, **kwargs)

    def print_usage(self, tasks_module, short=False):
        tasks = self.load_tasks(tasks_module)
        if tasks:
            sorted_tasks = sorted(tasks)
            if short:
                print('Available tasks:', ', '.join(sorted_tasks))
            else:
                hr = get_hr()
                print_header('Available tasks:\n')
                for name in sorted_tasks:
                    task = tasks[name]
                    task_hr = hr[len(name) + 1:]
                    print_info(name, task_hr)
                    print('\n', task.usage, '\n', sep='')
        else:
            print_warning('No tasks available')


class TaskRunnerError(Exception):

    pass
