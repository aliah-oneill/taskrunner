import argparse
import inspect
import os
import time
from collections import OrderedDict

from .util import Hide, cached_property, get_hr, print_debug, print_info


__all__ = ['task']


class Task:

    def __init__(self, implementation, name=None, description=None, help=None, type=None,
                 default_env=None, timed=False):
        self.implementation = implementation
        self.name = name or implementation.__name__
        self.description = description
        self.help_text = help or {}
        self.types = type or {}
        self.default_env = default_env or os.environ.get('TASKRUNNER_DEFAULT_ENV')
        self.timed = timed

        self.qualified_name = '.'.join((implementation.__module__, implementation.__qualname__))
        self.defaults_path = '.'.join(('defaults', self.qualified_name))

    @classmethod
    def decorator(cls, name_or_wrapped=None, description=None, help=None, type=None,
                  default_env=None, timed=False):
        if callable(name_or_wrapped):
            wrapped = name_or_wrapped
            name = wrapped.__name__
            return Task(
                implementation=wrapped,
                name=name,
                description=description,
                help=help,
                type=type,
                default_env=default_env,
                timed=timed,
            )
        else:
            name = name_or_wrapped

        def wrapper(wrapped):
            return Task(
                implementation=wrapped,
                name=name,
                description=description,
                help=help,
                type=type,
                default_env=default_env,
                timed=timed,
            )
        return wrapper

    def run(self, config, args):
        if self.timed:
            start_time = time.monotonic()

        kwargs = self.parse_args(config, args)
        result = self(config, **kwargs)

        if self.timed:
            hide = kwargs.get('hide', config._get_dotted('run.hide', 'none'))
            hide = Hide(hide) if hide is not None else Hide.none
            if hide not in (Hide.stdout, Hide.all):
                self.print_elapsed_time(time.monotonic() - start_time)

        return result

    def __call__(self, config, *args, **kwargs):
        if config.debug:
            print_debug('Task called:', self.name)
            print_debug('    Received positional args:', args)
            print_debug('    Received keyword args:', kwargs)

        defaults = config._get_dotted(self.defaults_path, None)
        if defaults:
            positionals = OrderedDict()
            for name, value in zip(self.positionals, args):
                positionals[name] = value

            for name in self.positionals:
                present = name in positionals or name in kwargs
                if not present and name in defaults:
                    kwargs[name] = defaults[name]

            for name in self.optionals:
                present = name in kwargs
                if not present and name in defaults:
                    kwargs[name] = defaults[name]

        if 'echo' in self.parameters and 'echo' not in kwargs:
            kwargs['echo'] = config._get_dotted('run.echo', False)

        if 'hide' in self.parameters and 'hide' not in kwargs:
            kwargs['hide'] = config._get_dotted('run.hide', 'none')

        if config.debug:
            print_debug('Running task:', self.name)
            print_debug('    Final positional args:', repr(args))
            print_debug('    Final keyword args:', repr(kwargs))

        return self.implementation(config, *args, **kwargs)

    def parse_args(self, config, args):
        if config.debug:
            print_debug('Parsing args for task `{self.name}`: {args}'.format(**locals()))
        parsed_args = self.get_arg_parser(config).parse_args(args)
        parsed_args = vars(parsed_args)
        return parsed_args

    def arg_names_for_param(self, param):
        params = self.parameters
        param = params[param] if isinstance(param, str) else param
        name = param.name

        if param.is_positional:
            return [name]

        arg_names = []
        arg_name = name.replace('_', '-')
        short_name = '-{arg_name[0]}'.format(arg_name=arg_name)
        long_name = '--{arg_name}'.format(arg_name=arg_name)

        first_char = name[0]
        names_that_start_with_first_char = [n for n in params if n.startswith(first_char)]
        names_that_start_with_first_char += [None, None]
        if names_that_start_with_first_char[0] == name:
            arg_names.append(short_name)
        elif names_that_start_with_first_char[1] == name:
            arg_names.append(short_name.upper())

        arg_names.append(long_name)

        if param.is_bool:
            if name == 'yes':
                no_long_name = '--no'
            elif name == 'no':
                no_long_name = '--yes'
            else:
                no_long_name = '--no-{name}'.format(name=arg_name)
            arg_names.append(no_long_name)

        return arg_names

    def print_elapsed_time(self, elapsed_time):
        m, s = divmod(elapsed_time, 60)
        m = int(m)
        hr = get_hr()
        msg = '{hr}\nElapsed time for {self.name} task: {m:d}m {s:.3f}s\n{hr}'.format(**locals())
        print_info(msg)

    @cached_property
    def signature(self):
        return inspect.signature(self.implementation)

    @cached_property
    def parameters(self):
        parameters = tuple(self.signature.parameters.items())[1:]
        params = OrderedDict()
        position = 1
        for name, param in parameters:
            if param.default is param.empty:
                param_position = position
                position += 1
            else:
                param_position = None
            params[name] = Parameter(param, param_position)
        return params

    @cached_property
    def positionals(self):
        parameters = self.parameters.items()
        return OrderedDict((n, p) for (n, p) in parameters if p.is_positional)

    @cached_property
    def optionals(self):
        parameters = self.parameters.items()
        return OrderedDict((n, p) for (n, p) in parameters if p.is_optional)

    @cached_property
    def arg_map(self):
        """Map command-line arg names to parameters."""
        arg_map = OrderedDict()
        for param in self.parameters.values():
            arg_names = self.arg_names_for_param(param)
            for arg_name in arg_names:
                arg_map[arg_name] = param
        return arg_map

    @cached_property
    def param_map(self):
        """Map parameters to command-line arg names."""
        parameters = self.parameters.items()
        return OrderedDict((n, self.arg_names_for_param(p)) for (n, p) in parameters)

    def get_arg_parser(self, config=None):
        if self.description:
            description = self.description
        else:
            docstring = self.implementation.__doc__
            if docstring:
                description = []
                for line in docstring.strip().splitlines():
                    line = line.strip()
                    if line:
                        description.append(line)
                    else:
                        break
                description = ' '.join(description) or None
            else:
                description = None

        parser = argparse.ArgumentParser(
            prog=self.name,
            description=description,
            add_help=False,
            argument_default=argparse.SUPPRESS,
        )

        # Manually add help arg so we can control its option name(s).
        parser.add_argument(
            '--help', action='help', default=argparse.SUPPRESS,
            help='Show this help message and exit')

        defaults = config._get_dotted(self.defaults_path, {}) if config else {}

        for name, arg_names in self.param_map.items():
            param = self.parameters[name]

            if param.is_positional and name in defaults:
                default = defaults[name]
            else:
                default = param.default

            kwargs = {
                'help': self.help_text.get(name),
            }

            if name in self.types:
                kwargs['type'] = self.types[name]
            elif not param.is_bool:
                for type_ in (int, float, complex):
                    if isinstance(default, type_):
                        kwargs['type'] = type_

            if param.is_positional:
                # Make positionals optional if a default value is
                # specified via config.
                if default is not param.empty:
                    kwargs['nargs'] = '?'
                    kwargs['default'] = default
                parser.add_argument(*arg_names, **kwargs)
            else:
                kwargs['dest'] = name
                if param.is_bool:
                    parser.add_argument(*arg_names[:-1], action='store_true', **kwargs)
                    parser.add_argument(arg_names[-1], action='store_false', **kwargs)
                else:
                    parser.add_argument(*arg_names, **kwargs)

        return parser

    @property
    def help(self):
        help_ = self.get_arg_parser().format_help()
        help_ = help_.split(': ', 1)[1]
        help_ = help_.strip()
        return help_

    @property
    def usage(self):
        usage = self.get_arg_parser().format_usage()
        usage = usage.split(': ', 1)[1]
        usage = usage.strip()
        return usage

    def __hash__(self):
        return hash(self.name)

    def __str__(self):
        return self.usage

    def partition_args(self, args):
        """Partition list of args into positionals & optionals.

        Args:
            args (list)

        Returns:
            (OrderedDict, OrderedDict)

        Usage::

            positionals, optionals = self.partition_args(args)
            defaults = self.defaults
            if defaults:
                for name in self.positionals:
                    if name not in positionals and name in defaults:
                        args.append(defaults[name])

        .. todo:: Remove this since it's unused.

        """
        i = 0
        all_positionals = list(self.positionals.values())
        positional_index = 0
        force_positional = False
        positionals = OrderedDict()
        optionals = OrderedDict()
        while i < len(args):
            item = args[i]
            positional = force_positional or not item.startswith('-')
            if item == '--':
                i += 1
                force_positional = True
            elif positional:
                try:
                    param = all_positionals[positional_index]
                except IndexError:
                    # Too many positionals; bail
                    break
                positionals[param.name] = item
                positional_index += 1
                i += 1
            else:
                if item == '--help':
                    i += 1
                else:
                    try:
                        param = self.arg_map[item]
                    except KeyError:
                        # Unknown optional; bail
                        break
                    optionals[param.name] = item
                    if param.is_bool:
                        i += 1
                    else:
                        if '=' in item:
                            i += 1
                        else:
                            i += 2
        return positionals, optionals


task = Task.decorator


class Parameter:

    def __init__(self, parameter, position):
        self._parameter = parameter
        self.is_bool = isinstance(parameter.default, bool)
        self.is_positional = parameter.default is parameter.empty
        self.is_optional = not self.is_positional
        self.position = position

    def __getattr__(self, name):
        return getattr(self._parameter, name)


# Avoid circular import
from .config import RawConfig
