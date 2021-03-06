import argparse
import os
import sys
import textwrap

from .runner import TaskRunner, TaskRunnerError
from .util import print_debug, print_error, print_warning


def main(argv=None):
    """Run one or more tasks in succession.

    For example, assume the tasks ``local`` and ``remote`` have been
    defined; the following will run ``ls`` first on the local host and
    then on the remote hos::

        runtasks local ls remote --host <host> ls

    When a task name is encountered in ``argv``, it will be considered
    the starting point of the next task *unless* the previous item in
    ``arv`` was an option like ``--xyz`` that expects a value (i.e.,
    it's not a flag).

    To avoid ambiguity when an option value matches a task name, the
    value can be prepended with a colon to force it to be considered
    a value and not a task name.

    """
    argv = sys.argv[1:] if argv is None else argv
    command_args, remaining_args = split_args(argv)

    parser = argparse.ArgumentParser(
        description=textwrap.dedent(''.join(('    ', main.__doc__.strip()))),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument('-c', '--config-file', type=config_file_type, default='tasks.cfg')
    parser.add_argument('-e', '--env', type=config_file_type, default=None)
    parser.add_argument('-t', '--tasks-module', default='tasks.py')
    parser.add_argument('-l', dest='list_tasks_short', action='store_true', default=False)
    parser.add_argument('--list', dest='list_tasks', action='store_true', default=False)
    parser.add_argument('-E', '--echo', action='store_true', default=False)
    parser.add_argument('--no-echo', action='store_false', dest='echo', default=False)
    parser.add_argument('--hide', choices=('none', 'stdout', 'stderr', 'all'), default=None)
    parser.add_argument('-d', '--debug', action='store_true', default=False)
    args = parser.parse_args(command_args)

    if args.debug:
        print_debug('All args:', argv)
        print_debug('Runtasks args:', command_args)
        print_debug('All task args:', remaining_args)
        args.echo = True

    runner = TaskRunner(
        config_file=args.config_file,
        env=args.env,
        tasks_module=args.tasks_module,
        default_echo=args.echo,
        default_hide=args.hide,
        debug=args.debug,
    )

    if args.list_tasks_short:
        runner.print_usage(args.tasks_module, short=True)
    elif args.list_tasks:
        runner.print_usage(args.tasks_module)
    elif not remaining_args:
        print_warning('No tasks specified\n')
        runner.print_usage(args.tasks_module)
    else:
        try:
            runner.run(remaining_args)
        except TaskRunnerError as exc:
            print_error(exc, file=sys.stderr)
            return 1

    return 0


def split_args(argv):
    command_args = []

    options_with_values = {'-c', '--config-file', '-e', '--env', '-t', '--tasks-module', '--hide'}
    option_value_expected = False

    for i, s in enumerate(argv):
        if s.startswith('-'):
            command_args.append(s)
            if s in options_with_values:
                option_value_expected = '=' not in s
        elif option_value_expected:
            command_args.append(s)
            option_value_expected = False
        else:
            remaining_args = argv[i:]
            break
    else:
        # No args or all args consumed
        remaining_args = []

    return command_args, remaining_args


def config_file_type(value):
    if value == 'tasks.cfg':
        if not os.path.isfile('tasks.cfg'):
            value = None
    return value


if __name__ == '__main__':
    sys.exit(main())
