"""
Look inside HDF5 files from the terminal, especially those created by deepdish.
"""
from __future__ import division, print_function, absolute_import
from .hdf5io import (DEEPDISH_IO_VERSION_STR, DEEPDISH_IO_PREFIX,
                     DEEPDISH_IO_UNPACK, DEEPDISH_IO_ROOT_IS_SNS,
                     IO_VERSION, _sns, is_pandas_dataframe)
import tables
import numpy as np
import sys
import os
from deepdish import io, six, __version__

LEFT_COL = 25

COLORS = dict(
    black='0;30',
    darkgray='1;30',
    red='1;31',
    green='1;32',
    brown='0;33',
    yellow='1;33',
    blue='1;34',
    purple='1;35',
    cyan='1;36',
    white='1;37',
    reset='0'
)


def _pandas_shape(level):
    if 'ndim' in level._v_attrs:
        ndim = level._v_attrs['ndim']
        shape = []
        for i in range(ndim):
            axis_name = 'axis{}'.format(i)
            if axis_name in level._v_children:
                axis = len(level._v_children[axis_name])
                shape.append(axis)
            elif axis_name + '_label0' in level._v_children:
                axis = len(level._v_children[axis_name + '_label0'])
                shape.append(axis)
            else:
                return None
        return tuple(shape)


def paint(s, color, colorize=True):
    if colorize:
        if color in COLORS:
            return '\033[{}m{}\033[0m'.format(COLORS[color], s)
        else:
            raise ValueError('Invalid color')
    else:
        return s


def type_string(typename, dtype=None, extra=None,
                type_color='red', colorize=True):
    ll = [paint(typename, type_color, colorize=colorize)]
    if extra:
        ll += [extra]
    if dtype:
        ll += [paint('[' + dtype + ']', 'darkgray', colorize=colorize)]

    return ' '.join(ll)


def container_info(name, size=None, colorize=True, type_color=None,
                   final_level=False):
    if final_level:
        d = {}
        if size is not None:
            d['extra'] = '(' + str(size) + ')'
        if type_color is not None:
            d['type_color'] = type_color

        s = type_string(name, colorize=colorize, **d)
        # Mark that it's abbreviated
        s += ' ' + paint('[...]', 'darkgray', colorize=colorize)
        return s

    else:
        # If not abbreviated, then display the type in dark gray, since
        # the information is already conveyed through the children
        return type_string(name, colorize=colorize, type_color='darkgray')


def abbreviate(s, maxlength=25):
    """Color-aware abbreviator"""
    assert maxlength >= 4
    skip = False
    abbrv = None
    i = 0
    for j, c in enumerate(s):
        if c == '\033':
            skip = True
        elif skip:
            if c == 'm':
                skip = False
        else:
            i += 1

        if i == maxlength - 1:
            abbrv = s[:j] + '\033[0m...'
        elif i > maxlength:
            break

    if i <= maxlength:
        return s
    else:
        return abbrv


def print_row(key, value, level=0, parent='/', colorize=True,
              file=sys.stdout, unpack=False):
    s = '{}{}'.format(paint(parent, 'darkgray', colorize=colorize),
                      paint(key, 'white', colorize=colorize))
    s_raw = '{}{}'.format(parent, key)
    if unpack:
        extra_str = '*'
        s_raw += extra_str
        s += paint(extra_str, 'purple', colorize=colorize)
    print('{}{} {}'.format(abbreviate(s, LEFT_COL),
                           ' '*max(0, (LEFT_COL + 1 - len(s_raw))),
                           value))


class Node(object):
    def __repr__(self):
        return 'Node'

    def print(self, level=0, parent='/', colorize=True, max_level=None,
              file=sys.stdout):
        pass

    def info(self, colorize=True, final_level=False):
        return paint('Node', 'red', colorize=colorize)


class FileNotFoundNode(Node):
    def __init__(self, filename):
        self.filename = filename

    def __repr__(self):
        return 'FileNotFoundNode'

    def print(self, level=0, parent='/', colorize=True, max_level=None,
              file=sys.stdout):
        print(paint('File not found', 'red', colorize=colorize),
              file=file)

    def info(self, colorize=True, final_level=False):
        return paint('FileNotFoundNode', 'red', colorize=colorize)


class InvalidFileNode(Node):
    def __init__(self, filename):
        self.filename = filename

    def __repr__(self):
        return 'InvalidFileNode'

    def print(self, level=0, parent='/', colorize=True, max_level=None,
              file=sys.stdout):
        print(paint('Invalid HDF5 file', 'red', colorize=colorize),
              file=file)

    def info(self, colorize=True, final_level=False):
        return paint('InvalidFileNode', 'red', colorize=colorize)


class DictNode(Node):
    def __init__(self):
        self.children = {}
        self.header = {}

    def add(self, k, v):
        self.children[k] = v

    def print(self, level=0, parent='/', colorize=True, max_level=None,
              file=sys.stdout):
        if level == 0 and not self.header.get('dd_io_unpack'):
            print_row('', self.info(colorize=colorize,
                                    final_level=(0 == max_level)),
                      level=level, parent=parent, unpack=False,
                      colorize=colorize, file=file)
        if level < max_level:
            for k in sorted(self.children):
                v = self.children[k]
                final = level+1 == max_level

                print_row(k, v.info(colorize=colorize,
                                    final_level=final), level=level,
                          parent=parent, unpack=self.header.get('dd_io_unpack'),
                          colorize=colorize, file=file)
                v.print(level=level+1, parent='{}{}/'.format(parent, k),
                        colorize=colorize, max_level=max_level, file=file)

    def info(self, colorize=True, final_level=False):
        return container_info('dict', size=len(self.children),
                              colorize=colorize,
                              type_color='purple',
                              final_level=final_level)

    def __repr__(self):
        s = ['{}={}'.format(k, repr(v)) for k, v in self.children.items()]
        return 'DictNode({})'.format(', '.join(s))


class SimpleNamespaceNode(DictNode):
    def info(self, colorize=True, final_level=False):
        return container_info('SimpleNamespace', size=len(self.children),
                              colorize=colorize,
                              type_color='purple',
                              final_level=final_level)

    def __repr__(self):
        s = ['{}={}'.format(k, repr(v)) for k, v in self.children.items()]
        return 'SimpleNamespaceNode({})'.format(', '.join(s))


class PandasDataFrameNode(Node):
    def __init__(self, shape):
        self.shape = shape

    def info(self, colorize=True, final_level=False):
        d = {}
        if self.shape is not None:
            d['extra'] = repr(self.shape)

        return type_string('DataFrame',
                           type_color='red',
                           colorize=colorize, **d)

    def __repr__(self):
        return 'PandasDataFrameNode({})'.format(self.shape)


class PandasPanelNode(Node):
    def __init__(self, shape):
        self.shape = shape

    def info(self, colorize=True, final_level=False):
        d = {}
        if self.shape is not None:
            d['extra'] = repr(self.shape)

        return type_string('Panel',
                           type_color='red',
                           colorize=colorize, **d)

    def __repr__(self):
        return 'PandasPanelNode({})'.format(self.shape)


class PandasSeriesNode(Node):
    def __init__(self, size, dtype):
        self.size = size
        self.dtype = dtype

    def info(self, colorize=True, final_level=False):
        d = {}
        if self.size is not None:
            d['extra'] = repr((self.size,))
        if self.dtype is not None:
            d['dtype'] = str(self.dtype)

        return type_string('Series',
                           type_color='red',
                           colorize=colorize, **d)

    def __repr__(self):
        return 'SeriesNode()'


class ListNode(Node):
    def __init__(self, typename='list'):
        self.children = []
        self.typename = typename

    def append(self, v):
        self.children.append(v)

    def __repr__(self):
        s = [repr(v) for v in self.children]
        return 'ListNode({})'.format(', '.join(s))

    def print(self, level=0, parent='/', colorize=True,
              max_level=None, file=sys.stdout):
        if level < max_level:
            for i, v in enumerate(self.children):
                k = str(i)
                final = level + 1 == max_level
                print_row(k, v.info(colorize=colorize,
                                    final_level=final),
                          level=level, parent=parent + 'i',
                          colorize=colorize, file=file)
                v.print(level=level+1, parent='{}{}/'.format(parent + 'i', k),
                        colorize=colorize, max_level=max_level, file=file)

    def info(self, colorize=True, final_level=False):
        return container_info(self.typename, size=len(self.children),
                              colorize=colorize,
                              type_color='purple',
                              final_level=final_level)


class NumpyArrayNode(Node):
    def __init__(self, shape, dtype):
        self.shape = shape
        self.dtype = dtype

    def info(self, colorize=True, final_level=False):
        return type_string('array', extra=repr(self.shape),
                           dtype=str(self.dtype),
                           type_color='red',
                           colorize=colorize)

    def __repr__(self):
        return ('NumpyArrayNode(shape={}, dtype={})'
                .format(self.shape, self.dtype))


class SparseMatrixNode(Node):
    def __init__(self, fmt, shape, dtype):
        self.sparse_format = fmt
        self.shape = shape
        self.dtype = dtype

    def info(self, colorize=True, final_level=False):
        return type_string('sparse {}'.format(self.sparse_format),
                           extra=repr(self.shape),
                           dtype=str(self.dtype),
                           type_color='red',
                           colorize=colorize)

    def __repr__(self):
        return ('NumpyArrayNode(shape={}, dtype={})'
                .format(self.shape, self.dtype))


class ValueNode(Node):
    def __init__(self, value):
        self.value = value

    def __repr__(self):
        return 'ValueNode(type={})'.format(type(self.value))

    def info(self, colorize=True, final_level=False):
        if isinstance(self.value, six.text_type):
            if len(self.value) > 25:
                s = repr(self.value[:22] + '...')
            else:
                s = repr(self.value)

            return type_string(s, dtype='unicode',
                               type_color='green',
                               extra='({})'.format(len(self.value)),
                               colorize=colorize)
        if isinstance(self.value, six.binary_type):
            if len(self.value) > 25:
                s = repr(self.value[:22] + b'...')
            else:
                s = repr(self.value)

            return type_string(s, dtype='ascii',
                               type_color='green',
                               extra='({})'.format(len(self.value)),
                               colorize=colorize)
        elif self.value is None:
            return type_string('None', dtype='python',
                               type_color='blue',
                               colorize=colorize)
        else:
            return type_string(repr(self.value),
                               dtype=str(np.dtype(type(self.value))),
                               type_color='blue',
                               colorize=colorize)


class ObjectNode(Node):
    def __init__(self):
        pass

    def __repr__(self):
        return 'ObjectNode'

    def info(self, colorize=True, final_level=False):
        return type_string('pickled', dtype='object', type_color='yellow',
                           colorize=colorize)


def _tree_level(level, raw=False):
    if isinstance(level, tables.Group):
        if _sns and (level._v_title.startswith('sns:') or
                     DEEPDISH_IO_ROOT_IS_SNS in level._v_attrs):
            node = SimpleNamespaceNode()
        else:
            node = DictNode()

        for grp in level:
            node.add(grp._v_name, _tree_level(grp, raw=raw))

        for name in level._v_attrs._f_list():
            v = level._v_attrs[name]
            if name == DEEPDISH_IO_VERSION_STR:
                node.header['dd_io_version'] = v

            if name == DEEPDISH_IO_UNPACK:
                node.header['dd_io_unpack'] = v

            if name.startswith(DEEPDISH_IO_PREFIX):
                continue

            node.add(name, ValueNode(v))

        if (level._v_title.startswith('list:') or
                level._v_title.startswith('tuple:')):
            s = level._v_title.split(':', 1)[1]
            N = int(s)
            lst = ListNode(typename=level._v_title.split(':')[0])
            for i in range(N):
                t = node.children['i{}'.format(i)]
                lst.append(t)
            return lst
        elif level._v_title.startswith('nonetype:'):
            return ValueNode(None)
        elif is_pandas_dataframe(level):
            pandas_type = level._v_attrs['pandas_type']
            if raw:
                # Treat as regular dictionary
                pass
            elif pandas_type == 'frame':
                shape = _pandas_shape(level)
                new_node = PandasDataFrameNode(shape)
                return new_node
            elif pandas_type == 'series':
                try:
                    values = level._v_children['values']
                    size = len(values)
                    dtype = values.dtype
                except:
                    size = None
                    dtype = None
                new_node = PandasSeriesNode(size, dtype)
                return new_node
            elif pandas_type == 'wide':
                shape = _pandas_shape(level)
                new_node = PandasPanelNode(shape)
                return new_node
            # else: it will simply be treated as a dict

        elif level._v_title.startswith('sparse:') and not raw:
            frm = level._v_attrs.format
            dtype = level.data.dtype
            shape = tuple(level.shape[:])
            node = SparseMatrixNode(frm, shape, dtype)
            return node

        return node
    elif isinstance(level, tables.VLArray):
        if level.shape == (1,):
            return ObjectNode()
        node = NumpyArrayNode(level.shape, 'unknown')
        return node
    elif isinstance(level, tables.Array):
        node = NumpyArrayNode(level.shape, level.dtype)
        if hasattr(level._v_attrs, 'strtype'):
            strtype = level._v_attrs.strtype
            itemsize = level._v_attrs.itemsize
            if strtype == b'unicode':
                shape = level.shape[:-1] + (level.shape[-1] // itemsize // 4,)
            elif strtype == b'ascii':
                shape = level.shape

            node = NumpyArrayNode(shape, strtype.decode('ascii'))

        return node
    else:
        return Node()


def get_tree(path, raw=False):
    fn = os.path.basename(path)
    try:
        with tables.open_file(path, mode='r') as h5file:
            grp = h5file.root
            s = _tree_level(grp, raw=raw)
            s.header['filename'] = fn
            return s
    except OSError:
        return FileNotFoundNode(fn)
    except tables.exceptions.HDF5ExtError:
        return InvalidFileNode(fn)


def main():
    import argparse
    parser = argparse.ArgumentParser(
            description=("Look inside HDF5 files. Works particularly well "
                         "for HDF5 files saved with deepdish.io.save()."),
            prog='ddls',
            epilog='example: ddls test.h5 -i /foo/bar --ipython')
    parser.add_argument('file', nargs='+',
                        help='filename of HDF5 file')
    parser.add_argument('-d', '--depth', type=int, default=4,
                        help='max depth, defaults to 4')
    parser.add_argument('-nc', '--no-color', action='store_true',
                        help='turn off bash colors')
    parser.add_argument('-i', '--inspect', metavar='GRP',
                        help='prints a specific variable (e.g. /data)')
    parser.add_argument('--ipython', action='store_true',
                        help=('loads file into an IPython session.'
                              'Works with -i'))
    parser.add_argument('--raw', action='store_true',
                        help=('prints the raw HDF5 structure for complex '
                              'data types, such as sparse matrices and pandas '
                              'data frames'))
    parser.add_argument('-v', '--version', action='version',
                        version='deepdish {} (io protocol {})'.format(__version__, IO_VERSION))

    args = parser.parse_args()

    colorize = sys.stdout.isatty() and not args.no_color

    def single_file(files):
        if len(files) >= 2:
            s = 'Error: Select a single file when using --inspect'
            print(paint(s, 'red', colorize=colorize))
            sys.exit(1)
        return files[0]

    def run_ipython(fn, group=None, data=None):
        file_desc = paint(fn, 'yellow', colorize=colorize)
        if group is None:
            path_desc = file_desc
        else:
            path_desc = '{}:{}'.format(
                file_desc,
                paint(group, 'white', colorize=colorize))

        welcome = "Loaded {} into '{}':".format(
            path_desc,
            paint('data', 'blue', colorize=colorize))

        # Import deepdish for the session
        import deepdish as dd
        import IPython
        IPython.embed(header=welcome)

    i = 0
    if args.inspect is not None:
        fn = single_file(args.file)

        try:
            data = io.load(fn, args.inspect)
        except ValueError:
            s = 'Error: Could not find group: {}'.format(args.inspect)
            print(paint(s, 'red', colorize=colorize))
            sys.exit(1)
        if args.ipython:
            run_ipython(fn, group=args.inspect, data=data)
        else:
            print(data)
    elif args.ipython:
        fn = single_file(args.file)
        data = io.load(fn)
        run_ipython(fn, data=data)
    else:
        for f in args.file:
            s = get_tree(f, raw=args.raw)
            if s is not None:
                if i > 0:
                    print()

                if len(args.file) >= 2:
                    print(paint(f, 'yellow', colorize=colorize))
                s.print(colorize=colorize, max_level=args.depth)
                i += 1


if __name__ == '__main__':
    main()
