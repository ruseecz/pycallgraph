from __future__ import division

import tempfile
import os
import textwrap

from ..metadata import __version__
from ..exceptions import PyCallGraphException
from .output import Output


# TODO: Move to base class or a helper image class
def colorize_node(node):
    value = float(node.time.fraction * 2 + node.calls.fraction) / 3
    return '%f %f %f' % (value / 2 + .5, value, 0.9)


def colorize_edge(node):
    value = float(node.time.fraction * 2 + node.calls.fraction) / 3
    return '%f %f %f' % (value / 2 + .5, value, 0.7)


class GraphvizOutput(Output):

    def __init__(self):
        self.tool = 'dot'
        self.output_file = 'pycallgraph.png'
        self.output_type = 'png'
        self.font_name = 'Verdana'
        self.font_size = 7
        self.group_font_size = 10
        self.group_border_color = '.5 0 .9'

        self.node_label = r'\n'.join([
            '%(func)s',
            'calls: %(hits)i',
            'total time: %(total_time)f',
        ])

        self.memory_node_label = \
            r'\nmemory in: %(total_memory_in)s' \
            r'\nmemory out: %(total_memory_out)s'

        self.node_color_func = colorize_node
        self.edge_color_func = colorize_edge

        self.time_filter = None

        self.prepare_graph_attributes()

    @classmethod
    def add_arguments(cls, subparsers, parent_parser, usage):
        defaults = cls()

        subparser = subparsers.add_parser(
            'graphviz', help='Graphviz generation',
            parents=[parent_parser], usage=usage,
        )

        subparser.add_argument(
            '-t', '--tool', dest='tool', default='dot',
            help='The tool from Graphviz to use, e.g. dot, neato, etc.',
        )

        cls.add_output_file(
            subparser, defaults, 'The generated Graphviz file'
        )

        subparser.add_argument(
            '-f', '--output-format', type=str, default=defaults.output_type,
            help='Image format to produce, e.g. png, ps, dot, etc. '
            'See http://www.graphviz.org/doc/info/output.html for more.',
        )

        subparser.add_argument(
            '--font-name', type=str, default=defaults.font_name,
            help='Name of the font to be used',
        )

        subparser.add_argument(
            '--font-size', type=int, default=defaults.font_size,
            help='Size of the font to be used',
        )

    def sanity_check(self):
        self.ensure_binary(self.tool)

    def prepare_graph_attributes(self):
        generated_message = '\\n'.join([
            r'Generated by Python Call Graph v%s' % __version__,
            r'http://pycallgraph.slowchop.com',
        ])

        self.graph_attributes = {
            'graph': {
                'overlap': 'scalexy',
                'fontname': self.font_name,
                'fontsize': self.font_size,
                'fontcolor': '0 0 0.5',
                'label': generated_message,
            },
            'node': {
                'fontname': self.font_name,
                'fontsize': self.font_size,
                'color': '.5 0 .9',
                'style': 'filled',
                'shape': 'rect',
            },
            'edge': {
                'fontname': self.font_name,
                'fontsize': self.font_size,
                'color': '0 0 0',
            }
        }

    def done(self):
        source = self.generate()

        self.debug(source)

        fd, temp_name = tempfile.mkstemp()
        with os.fdopen(fd, 'w') as f:
            f.write(source)

        cmd = '{} -T{} -o{} {}'.format(
            self.tool, self.output_type, self.output_file, temp_name
        )

        try:
            ret = os.system(cmd)
            if ret:
                raise PyCallGraphException(
                    'The command "%(cmd)s" failed with error '
                    'code %(ret)i.' % locals())
        finally:
            os.unlink(temp_name)

        self.verbose('Generated {} with {} nodes.'.format(
            self.output_file, len(self.processor.func_count),
        ))

    def attrs_from_dict(self, d):
        output = []
        for attr, val in d.iteritems():
            output.append('%s = "%s"' % (attr, val))
        return ', '.join(output)

    def node(self, key, attr):
        return '"{}" [{}];'.format(
            key, self.attrs_from_dict(attr),
        )

    def generate_attributes(self):
        output = []
        for section, attrs in self.graph_attributes.iteritems():
            output.append('{} [ {} ];'.format(
                section, self.attrs_from_dict(attrs),
            ))
        return output

    def generate_groups(self):
        if not self.processor.config.groups:
            return ''

        output = []
        for group, funcs in self.processor.groups():
            funcs = '" "'.join(funcs)
            group_color = self.group_border_color
            group_font_size = self.group_font_size
            output.append(
                'subgraph "cluster_%(group)s" { '
                '"%(funcs)s"; '
                'label = "%(group)s"; '
                'node [style=filled]; '
                'fontsize = "%(group_font_size)s"; '
                'fontcolor = "black"; '
                'color="%(group_color)s"; }' % locals())
        return output

    def generate_nodes(self):
        output = []
        for node in self.processor.nodes():
            attr = {
                'color': self.node_color_func(node),
            }
            output.append(self.entry(node.name, attr))

        return output

        # for func, hits in self.processor.func_count.iteritems():
        #     # XXX: This line is pretty terrible. Maybe return an object?
        #     calls_frac, total_time_frac, total_time, total_memory_in_frac, \
        #         total_memory_in, total_memory_out_frac, total_memory_out = \
        #         self.processor.frac_calculation(func, hits)

        #     total_memory_in = self.human_readable_size(total_memory_in)
        #     total_memory_out = self.human_readable_size(total_memory_out)

        #     attribs = {
        #         'color': self.node_color_func(calls_frac, total_time_frac),
        #         # 'label': self.get_node_label()
        #         'label': func,
        #     }
        #     # attribs_str = '{}={}'.format(*[a for a in attribs.iteritems()])
        #     node_str = '"%s" [%s];' % (func, ' ')
        #     if self.time_filter is None or \
        #             self.time_filter.fraction <= total_time_frac:
        #         output.append(node_str % locals())
        # return output

    def generate_edges(self):
        output = []

        # for edge in self.processor.edges():

        for fr_key, fr_val in self.processor.call_dict.iteritems():
            if not fr_key:
                continue
            for to_key, to_val in fr_val.iteritems():
                # calls_frac, total_time_frac, total_time, \
                #     total_memory_in_frac, \
                #     total_memory_in, total_memory_out_frac, \
                #     total_memory_out = \
                #     self.processor.frac_calculation(to_key, to_val)
                # col = self.edge_color_func(calls_frac, total_time_frac)
                # edge = '[color = "%s", label="%s"]' % (col, to_val)
                # if self.time_filter is None or \
                #         self.time_filter.fraction < total_time_frac:
                edge = '[]'
                output.append(
                    '"%s" -> "%s" %s;' % (fr_key, to_key, edge))

        return output

    def generate(self):
        indent_join = '\n' + ' ' * 12

        return textwrap.dedent('''\
        digraph G {{

            // Attributes
            {}

            // Groups
            {}

            // Nodes
            {}

            // Edges
            {}

        }}
        '''.format(
            indent_join.join(self.generate_attributes()),
            indent_join.join(self.generate_groups()),
            indent_join.join(self.generate_nodes()),
            indent_join.join(self.generate_edges()),
        ))
