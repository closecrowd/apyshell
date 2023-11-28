#!/usr/bin/env python3
"""Safe(ish) evaluation of mathematical expression using Python's ast
module.

Extensively modified by Mark Anacker <closecrowd@pm.me>

Forked from:
https://github.com/newville/asteval

This module provides an Interpreter class that compiles a restricted set of
Python expressions and statements to Python's AST representation, and then
executes that representation using values held in a symbol table.  It is
meant to be instanciated by the ApyEngine class in apyengine.py.

The symbol table is a simple dictionary, giving a simple, flat namespace.
This comes pre-loaded with many functions from Python's builtin and math
module.  If numpy is installed, many numpy functions are also included.
Additional symbols can be added when an Interpreter is created, but the
user of that interpreter will not be able to import additional modules.
Access to the symbol table is protected by a mutex, allowing multiple
threads to access the global state without interfering with each other.

Expressions, including loops, conditionals, and function definitions can be
compiled into ast node and then evaluated later, using the current values
in the symbol table.

The result is a restricted, simplified version of Python that is somewhat
safer than 'eval' because many unsafe operations (such as 'import' and
'eval') are simply not allowed.

Many parts of Python syntax are supported, including:
    * for loops, while loops, if-then-elif-else conditionals
    * try-except (including 'finally')
    * function definitions with def
    * advanced slicing:    a[::-1], array[-3:, :, ::2]
    * if-expressions:      out = one_thing if TEST else other
    * list comprehension   out = [sqrt(i) for i in values]

The following Python syntax elements are not supported:
     Import, Exec, Lambda, Class, Global, Generators, Yield, Decorators

In addition, while many builtin functions are supported, several builtin
functions that are considered unsafe are missing ('exec', and
'getattr' for example)

Credits:
   * version: 1.0
   * last update: 2018-Sept-29
   * License:  MIT
   * Author:  Mark Anacker <closecrowd@pm.me>
   * Copyright (c) 2023 by Mark Anacker

Note:
   * Based on: asteval 0.9.13    <https://github.com/newville/asteval>
   * Originally by: Matthew Newville, Center for Advanced Radiation Sources,
     The University of Chicago, <newville@cars.uchicago.edu>

"""

from __future__ import division, print_function

from types import *
import ast
import time
import inspect
from sys import exc_info, stdout, stderr, version_info

from threading import RLock

from .astutils import (UNSAFE_ATTRS, make_symbol_table,
                       op2func, ExceptionHolder, ReturnedNone,
                       valid_symbol_name, install_python_module)

##############################################################################

#
# Globals
#

builtins = __builtins__
if not isinstance(builtins, dict):
    builtins = builtins.__dict__

ALL_NODES = ['arg', 'assert', 'assign', 'attribute', 'augassign', 'binop',
             'boolop', 'break', 'call', 'compare',  'constant', 'continue', 'delete',
             'dict', 'ellipsis', 'excepthandler', 'expr', 'extslice',
             'for', 'functiondef', 'if', 'ifexp', 'index', 'interrupt',
             'list', 'listcomp', 'module', 'name', 'nameconstant', 'num',
             'pass', 'raise', 'repr', 'return', 'slice', 'str',
             'subscript', 'try', 'tuple', 'unaryop', 'while']

symlock = RLock()

raise_errors = True

##############################################################################

# ----------------------------------------------------------------------------
#
# Interpreter class
#
# ----------------------------------------------------------------------------


class Interpreter(object):
    """Create an instance of the asteval Interpreter.

    This is the main class in this file.

    """

    def __init__(self, symtable=None, usersyms=None, writer=None,
                 err_writer=None, readonly_symbols=None, builtins_readonly=True,
                 global_funcs=False, max_statement_length=50000, no_print=False,
                 raise_errors=False):

        """Create an asteval Interpreter.

        This is a restricted, simplified interpreter using Python syntax.  This
        is meant to be called from the ApyEngine class in apyengine.py.

            Args:
                symtable : dictionary to use as symbol table (if `None`, one will be created).

                usersyms : dictionary of user-defined symbols to add to symbol table.

                writer : callable file-like object where standard output will be sent.

                err_writer : callable file-like object where standard error will be sent.

                readonly_symbols : symbols that the user can not assign to

                builtins_readonly : whether to blacklist all symbols that are in the initial symtable

                global_funcs : whether to make procs use the global symbol table

                max_statement_length : Maximum length of a script statement

                no_print : disable print() output if True

        """

        self.writer = writer or stdout
        self.err_writer = err_writer or stderr
        self.max_statement_length = max(1, min(1.e8, max_statement_length))

        self.modlist = []       # list of installed modules

        ## symtable
        if symtable is None:
            if usersyms is None:
                usersyms = {}
            symtable = make_symbol_table(self.modlist, **usersyms)

        symtable['print'] = self._printer   # install the print() function
        symtable['errline_'] = 0            # lineno of the last error
        self.no_print = no_print            # disable print entirely
        self.raise_errors = raise_errors

        self.symtable = symtable
        self._interrupt = None
        self.error = []
        self.error_msg = None
        self.expr = None
        self.retval = None
        self._calldepth = 0
        self.lineno = 0
        self.start_time = time.time()
        self.use_numpy = False
        self.globalsyms = global_funcs

        self.abort = False  # stop now with an exception
        self.stop = False   # stop soonest with no error

        nodes = ALL_NODES[:]

        self.node_handlers = {}
        for node in nodes:
            self.node_handlers[node] = getattr(self, "on_%s" % node)

        # to rationalize try/except try/finally for Python2.6 through Python3.3
        if 'try' in self.node_handlers:
            self.node_handlers['tryexcept'] = self.node_handlers['try']
            self.node_handlers['tryfinally'] = self.node_handlers['try']

        if readonly_symbols is None:
            self.readonly_symbols = {'errline_'}
        else:
            self.readonly_symbols = set(readonly_symbols)

        if builtins_readonly:
            self.readonly_symbols |= set(self.symtable)

        self.no_deepcopy = [key for key, val in symtable.items()
                            if (callable(val)
                                or 'numpy.lib.index_tricks' in repr(val)
                                or inspect.ismodule(val))]


    # stop a running script as soon as possible
    def abortrun(self):
        """Terminate execution of a script.

        Sets a flag that causes the currently-running script to exit
        as quickly as possible.

        """

        self.abort = True

    def stoprun(self):
        """Terminate execution of a script.

        Sets a flag that causes the currently-running script to exit
        as quickly as possible, without throwing an exception.

        """

        self.stop = True


    def remove_nodehandler(self, node):
        """Remove support for a node.

        Returns current node handler, so that it might be re-added
        with add_nodehandler()

        """

        out = None
        if node in self.node_handlers:
            out = self.node_handlers.pop(node)
        return out

    def set_nodehandler(self, node, handler):
        """set node handler"""
        self.node_handlers[node] = handler

    # import a pre-allowed Python module
    # see MODULE_LIST in astutils.py for the current list
    # of installable modules.  This is NOT the
    # extension loader.
    def install(self, modname):
        """Install a pre-authorized Python module into the engine's symbol table.

        This is callable from a script with the 'install_()' command.  Only modules
        in the MODULE_LIST list in astutils.py can be installed.  Once installed,
        they can not be uninstalled during this run of apyshell.

        This is called by the install_() function in apyengine.py

            Args:
                modname :   The module name to install
            Returns:
                The return value. True for success, False otherwise.
        """

        global symlock

        if not modname or len(modname) < 1:
            return False

        with symlock:
            # call the function in astutils.py to add the module
            rv = install_python_module(self.symtable, modname, self.modlist)

        # set a flag if we instaled numpy
        # this is used in on_compare()
        if rv:
            with symlock:
                if 'ndarray' in self.symtable:
                    self.use_numpy = True
        return rv

    def user_defined_symbols(self):
        """Return a set of symbols that have been added to symtable after
        construction.

        I.e., the symbols from self.symtable that are not in
        self.no_deepcopy.

            Args:
                None
            Returns:
                A set of symbols in symtable that are not in self.no_deepcopy

        """

        global symlock

        with symlock:
            sym_in_current = set(self.symtable.keys())
        sym_from_construction = set(self.no_deepcopy)
        unique_symbols = sym_in_current.difference(sym_from_construction)
        return unique_symbols

    def isReadOnly(self, varname):
        """See if a script variable name is marked read-only

        Script variables may be marked as read-only.  This will
        test that status.

            Args:
                varnam  :   The name of the variable
            Return:
                True is it's read-only
                False if it's read-write

        """

        if varname in self.readonly_symbols:
            return True
        return False

    # thread-safe add a symbol
    def addSymbol(self, name, val):
        global symlock

        with symlock:
            self.symtable[name] = val
        return True

    # thread-safe delete a symbol
    def delSymbol(self, name):
        global symlock

        with symlock:
            if name in self.symtable:
                del self.symtable[name]
            else:
                return False
        return True

    # thread-safe fetch a symbol
    def getSymbol(self, name):
        global symlock

        with symlock:
            if name in self.symtable:
                return self.symtable[name]
            else:
                return None
        return None



    def unimplemented(self, node):
        """Unimplemented nodes."""
        self.raise_exception(node, exc=NotImplementedError,
                             msg="'%s' is not supported" %
                             (node.__class__.__name__))

    def raise_exception(self, node, exc=None, msg='', expr=None,
                        lineno=0):
        global symlock

        ml = len(msg)

        """Add an exception."""
        if self.error is None:
            self.error = []
        if expr is None:
            expr = self.expr
        if len(self.error) > 0 and not isinstance(node, ast.Module):
            msg = '%s' % msg

        if node:
            if not isinstance(node, ast.Module):
                lineno = int(node.lineno)

        err = ExceptionHolder(node, exc=exc, msg=msg, expr=expr, lineno=lineno)
        self._interrupt = ast.Raise()
        self.error.append(err)

        if len(msg) > 0:
            self.error_msg = msg

        if lineno != 0 and ml > 0:
            self.error_msg = self.error_msg + ' at line '+str(lineno)

            with symlock:
                self.symtable['errline_'] = int(lineno)

        if exc is None:
            try:
                exc = self.error[0].exc
            except:
                exc = RuntimeError

        self.error[0].msg = self.error_msg
        raise exc(self.error_msg)

    # main entry point for Ast node evaluation
    #  parse:  text of statements -> ast
    #  run:    ast -> result
    #  eval:   string statement -> result = run(parse(statement))
    def parse(self, text):
        """Parse statement/expression to Ast representation."""

        if len(text) > self.max_statement_length:
            msg = 'length of text exceeds %d characters' % (self.max_statement_length)
            self.raise_exception(None, msg='Runtime Error', expr=msg)

        self.expr = text
        try:
            out = ast.parse(text)
        except SyntaxError:
            self.raise_exception(None, msg='Syntax Error', expr=text)
        except:
            self.raise_exception(None, msg='Parsing Error', expr=text)
        return out

    def run(self, node, expr=None, lineno=None, with_raise=True):
        """Execute parsed Ast representation for an expression."""

        # Note: keep the 'node is None' test: internal code here may run
        #    run(None) and expect a None in return.

        if self.stop:
            return None

        if self.abort:
            self.raise_exception(node, expr=None, msg='execution aborted')

        if len(self.error) > 0:
            return None

        if self.retval is not None:
            return self.retval
        if isinstance(self._interrupt, (ast.Break, ast.Continue)):
            return self._interrupt

        if node is None:
            return None
        if isinstance(node, str):
            node = self.parse(node)
        if lineno is not None:
            self.lineno = lineno
        if expr is not None:
            self.expr = expr

        # get handler for this node:
        #   on_xxx with handle nodes of type 'xxx', etc
        try:
            handler = self.node_handlers[node.__class__.__name__.lower()]
        except KeyError:
            return self.unimplemented(node)

        # run the handler:  this will likely generate
        # recursive calls into this run method.
        try:
            if str(type(node)) == "<class '_ast.Call'>":
                ret = handler(node)
            else:
                ret = handler(node)
            if isinstance(ret, enumerate):
                ret = list(ret)
            return ret
        except:
            if with_raise:
                self.raise_exception(node, expr=expr)

    def __call__(self, expr, **kw):
        """Call class instance as function."""

        return self.eval(expr, **kw)

    def eval(self, expr, lineno=0, show_errors=True):
        """Evaluate a single statement."""

        self.lineno = lineno
        self.error = []
        self.start_time = time.time()
        self.start_time = time.time()
        if isinstance(expr, str):
            if len(expr) > self.max_statement_length:
                msg = 'length of text exceeds %d characters' % (self.max_statement_length)
                raise ValueError(msg)

            try:
                node = self.parse(expr)
            except:
                errmsg = exc_info()[1]
                if len(self.error) > 0:
                    errmsg = "\n".join(self.error[0].get_error())
                if not show_errors:
                    try:
                        exc = self.error[0].exc
                    except:
                        exc = RuntimeError
                    raise exc(errmsg)
                print(errmsg, file=self.err_writer)
                return errmsg
        else:
            node = expr

        try:
            return self.run(node, expr=expr, lineno=lineno)
        except:
            errmsg = exc_info()[1]
            if len(self.error) > 0:
                errmsg = "\n".join(self.error[0].get_error())
            if self.raise_errors:
                try:
                    exc = self.error[0].exc
                except:
                    exc = RuntimeError
                raise exc(errmsg)
            if show_errors:
                print(errmsg, file=self.err_writer)

            print(errmsg, file=self.err_writer)
            return errmsg

    @staticmethod
    def dump(node, **kw):
        """Simple ast dumper."""

        return ast.dump(node, **kw)



    # handlers for ast components

    def on_expr(self, node):
        """Expression."""

        return self.run(node.value)  # ('value',)

    def on_index(self, node):
        """Index."""
        return self.run(node.value)  # ('value',)

    def on_return(self, node):  # ('value',)
        """Return statement: look for None, return special sentinal."""
        if self._calldepth == 0:
            raise SyntaxError('cannot return at top level')
        self.retval = self.run(node.value)
        if self.retval is None:
            self.retval = ReturnedNone
        return

    def on_repr(self, node):
        """Repr."""
        return repr(self.run(node.value))  # ('value',)

    def on_module(self, node):    # ():('body',)
        """Module def."""
        out = None
        for tnode in node.body:
            out = self.run(tnode)
        return out

    def on_expression(self, node):
        "basic expression"
        return self.on_module(node) # ():('body',)

    def on_pass(self, node):
        """Pass statement."""
        return None  # ()

    def on_ellipsis(self, node):
        """Ellipses."""
        return Ellipsis

    # for break and continue: set the instance variable _interrupt
    def on_interrupt(self, node):    # ()
        """Interrupt handler."""
        self._interrupt = node
        return node

    def on_break(self, node):
        """Break."""
        return self.on_interrupt(node)

    def on_continue(self, node):
        """Continue."""
        return self.on_interrupt(node)

    def on_assert(self, node):    # ('test', 'msg')
        """Assert statement."""
        if not self.run(node.test):
            self.raise_exception(node, exc=AssertionError, msg=node.msg)
        return True

    def on_list(self, node):    # ('elt', 'ctx')
        """List."""
        return [self.run(e) for e in node.elts]

    def on_tuple(self, node):    # ('elts', 'ctx')
        """Tuple."""
        return tuple(self.on_list(node))

    def on_dict(self, node):    # ('keys', 'values')
        """Dictionary."""
        return dict([(self.run(k), self.run(v)) for k, v in
                     zip(node.keys, node.values)])

    def on_constant(self, node):   # ('value', 'kind')
        """Return constant value."""
        return node.value

    def on_num(self, node):   # ('n',)
        """Return number."""
        return node.n

    def on_str(self, node):   # ('s',)
        """Return string."""
        return node.s

    def on_nameconstant(self, node):   # ('value',)
        """ named constant
            True, False, None in python >= 3.4 """
        return node.value

    def on_name(self, node):    # ('id', 'ctx')
        """Name node."""
        global symlock
        ctx = node.ctx.__class__
        if ctx in (ast.Param, ast.Del):
            return str(node.id)
        else:

            with symlock:
                if node.id in self.symtable:
                    return self.symtable[node.id]
                else:
                    msg = "name '%s' is not defined" % node.id
                    self.raise_exception(node, exc=NameError, msg=msg)

    def node_assign(self, node, val):
        """Assign a value (not the node.value object) to a node.

        This is used by on_assign, but also by for, list comprehension,
        etc.

        """
        global symlock

        # assignment in an except: statement comes here
        if isinstance(node, str):
            with symlock:
                self.symtable[node] = val
            return

        if node.__class__ == ast.Name:
            if not valid_symbol_name(node.id) or node.id in self.readonly_symbols:
                errmsg = "invalid symbol name (reserved word?) %s" % node.id
                self.raise_exception(node, exc=NameError, msg=errmsg)
            with symlock:
                self.symtable[node.id] = val
                if node.id in self.no_deepcopy:
                    self.no_deepcopy.remove(node.id)
                return

        elif node.__class__ == ast.Attribute:
            if node.ctx.__class__ == ast.Load:
                msg = "cannot assign to attribute %s" % node.attr
                self.raise_exception(node, exc=AttributeError, msg=msg)

            setattr(self.run(node.value), node.attr, val)

        elif node.__class__ == ast.Subscript:
            self.run(node.value)[self.run(node.slice)] = val

        elif node.__class__ in (ast.Tuple, ast.List):
            if len(val) == len(node.elts):
                for telem, tval in zip(node.elts, val):
                    self.node_assign(telem, tval)
            else:
                raise ValueError('too many values to unpack:'+str(len(val)))

    def on_attribute(self, node):    # ('value', 'attr', 'ctx')
        """Extract attribute."""
        ctx = node.ctx.__class__
        if ctx == ast.Store:
            msg = "attribute for storage: shouldn't be here!"
            self.raise_exception(node, exc=RuntimeError, msg=msg)

        sym = self.run(node.value)
        if ctx == ast.Del:
            return delattr(sym, node.attr)

        # ctx is ast.Load
        fmt = "cannnot access attribute '%s' for %s"
        if not (node.attr in UNSAFE_ATTRS or
                (node.attr.startswith('__') and
                 node.attr.endswith('__'))):
            fmt = "no attribute '%s' for %s"
            try:
                return getattr(sym, node.attr)
            except AttributeError:
                pass

        # AttributeError or accessed unsafe attribute
        obj = self.run(node.value)
        msg = fmt % (node.attr, obj)
        self.raise_exception(node, exc=AttributeError, msg=msg)

    def on_assign(self, node):    # ('targets', 'value')
        """Simple assignment."""

        val = self.run(node.value)

        for tnode in node.targets:
            self.node_assign(tnode, val)
        return

    def on_augassign(self, node):    # ('target', 'op', 'value')
        """Augmented assign."""
        return self.on_assign(ast.Assign(targets=[node.target],
                                         value=ast.BinOp(left=node.target,
                                                         op=node.op,
                                                         right=node.value)))

    def on_slice(self, node):    # ():('lower', 'upper', 'step')
        """Simple slice."""
        return slice(self.run(node.lower),
                     self.run(node.upper),
                     self.run(node.step))

    def on_extslice(self, node):    # ():('dims',)
        """Extended slice."""
        return tuple([self.run(tnode) for tnode in node.dims])

    def on_subscript(self, node):    # ('value', 'slice', 'ctx')
        """Subscript handling -- one of the tricky parts."""
        val = self.run(node.value)
        nslice = self.run(node.slice)
        ctx = node.ctx.__class__
        if ctx in (ast.Load, ast.Store):
            if nslice != None:
                if isinstance(node.slice, (ast.Index, ast.Slice, ast.Ellipsis)):
                    return val.__getitem__(nslice)
                elif isinstance(node.slice, ast.ExtSlice):
                    return val[nslice]
            else:
                self.raise_exception(node, msg="invalid slice in:"+str(val))
        else:
            msg = "subscript with unknown context"
            self.raise_exception(node, msg=msg)

    def on_delete(self, node):    # ('targets',)
        """Delete statement."""
        global symlock

        for tnode in node.targets:
            # make sure a script can't remove protected functions
            if tnode.id.endswith('_'):
                msg = "could not delete embedded proc: "+tnode.id
                self.raise_exception(node, msg=msg)

            if tnode.ctx.__class__ != ast.Del:
                break
            children = []
            while tnode.__class__ == ast.Attribute:
                children.append(tnode.attr)
                tnode = tnode.value

            if (tnode.__class__ == ast.Name and
                    tnode.id not in self.readonly_symbols):
                children.append(tnode.id)
                children.reverse()
                with symlock:
                    self.symtable.pop('.'.join(children))
            else:
                msg = "could not delete symbol"
                self.raise_exception(node, msg=msg)

    def on_unaryop(self, node):    # ('op', 'operand')
        """Unary operator."""
        return op2func(node.op)(self.run(node.operand))

    def on_binop(self, node):    # ('left', 'op', 'right')
        """Binary operator."""
        return op2func(node.op)(self.run(node.left),
                                self.run(node.right))

    def on_boolop(self, node):    # ('op', 'values')
        """Boolean operator."""
        val = self.run(node.values[0])
        is_and = ast.And == node.op.__class__
        if (is_and and val) or (not is_and and not val):
            for n in node.values[1:]:
                val = op2func(node.op)(val, self.run(n))
                if (is_and and not val) or (not is_and and val):
                    break
        return val

    def on_compare(self, node):  # ('left', 'ops', 'comparators')
        """comparison operators"""
        lval = self.run(node.left)
        out = True
        results = []
        for op, rnode in zip(node.ops, node.comparators):
            rval = self.run(rnode)
            ret = op2func(op)(lval, rval)
            results.append(ret)
            if ((self.use_numpy and not isinstance(ret, numpy.ndarray)) and
                    not ret):
                break
            lval = rval
        if len(results) == 1:
            return results[0]
        else:
            out = True
            for r in results:
                out = out and r
        return out

    def _printer(self, *out, **kws):
        """Generic print function.
            Optional arguments:
                prefix = '--> ' line prifix
                sep=' '         seperator between output arguments
                end = '\n'      line ending
                stderr = False  if True, output to stderr instead of stdout
                flush = True    if True, flush output immediately
        """

        # disable print() if set at entry time
        if self.no_print:
            return

        # get the output destination
        errout = kws.pop('stderr', False)
        if errout:
            fileh = self.err_writer
        else:
            fileh = self.writer

        # flush flag
        flush = kws.pop('flush', True)
        prefix = kws.pop('prefix', '--> ')
        sep = kws.pop('sep', ' ')
        end = kws.pop('end', '\n')

        if prefix != None:
            print(prefix, *out, file=fileh, sep=sep, end=end)
        else:
            print(*out, file=fileh, sep=sep, end=end)
        if flush:
            fileh.flush()

    def on_if(self, node):    # ('test', 'body', 'orelse')
        """Regular if-then-else statement."""
        block = node.body
        if not self.run(node.test):
            block = node.orelse
        for tnode in block:
            self.run(tnode)

    def on_ifexp(self, node):    # ('test', 'body', 'orelse')
        """If expressions."""
        expr = node.orelse
        if self.run(node.test):
            expr = node.body
        return self.run(expr)

    def on_while(self, node):    # ('test', 'body', 'orelse')
        """While blocks."""

        while self.run(node.test):
            self._interrupt = None
            for tnode in node.body:
                self.run(tnode)
                if self._interrupt is not None:
                    break
            if isinstance(self._interrupt, ast.Break):
                break
        else:
            for tnode in node.orelse:
                self.run(tnode)
        self._interrupt = None

    def on_for(self, node):    # ('target', 'iter', 'body', 'orelse', 'type_comment' )
        """For blocks."""

        for val in self.run(node.iter):
            self.node_assign(node.target, val)
            self._interrupt = None
            for tnode in node.body:
                self.run(tnode)
                if self._interrupt is not None:
                    break
            if isinstance(self._interrupt, ast.Break):
                break
        else:
            for tnode in node.orelse:
                self.run(tnode)

        self._interrupt = None

    def on_listcomp(self, node):    # ('elt', 'generators')
        """List comprehension -- only up to 4 generators!"""
        out = []
        locals = {}
        saved_syms = {}

        for tnode in node.generators:
            if tnode.__class__ == ast.comprehension:
                if tnode.target.__class__ == ast.Name:
                    if (not valid_symbol_name(tnode.target.id) or
                        tnode.target.id in self.readonly_symbols):
                        errmsg = "invalid symbol name (reserved word?) %s" % tnode.target.id
                        self.raise_exception(tnode.target, exc=NameError, msg=errmsg)
                    locals[tnode.target.id] = []
                    if tnode.target.id in self.symtable:
                        saved_syms[tnode.target.id] = copy.deepcopy(self.symtable[tnode.target.id])

                elif tnode.target.__class__ == ast.Tuple:
                    target = []
                    for tval in tnode.target.elts:
                        locals[tval.id] = []
                        if tval.id in self.symtable:
                            saved_syms[tval.id] = copy.deepcopy(self.symtable[tval.id])

        for tnode in node.generators:
            if tnode.__class__ == ast.comprehension:
#                tlist = []
                ttype = 'name'
                if tnode.target.__class__ == ast.Name:
                    if (not valid_symbol_name(tnode.target.id) or
                        tnode.target.id in self.readonly_symbols):
                        errmsg = "invalid symbol name (reserved word?) %s" % tnode.target.id
                        self.raise_exception(tnode.target, exc=NameError, msg=errmsg)
                    ttype, target = 'name', tnode.target.id
                elif tnode.target.__class__ == ast.Tuple:
                    ttype = 'tuple'
                    target =tuple([tval.id for tval in tnode.target.elts])

                for val in self.run(tnode.iter):
                    if ttype == 'name':
                        self.symtable[target] = val
                    else:
                        for telem, tval in zip(target, val):
                            self.symtable[target] = val

                    add = True
                    for cond in tnode.ifs:
                        add = add and self.run(cond)
                    if add:
                        if ttype == 'name':
                            locals[target].append(val)
                        else:
                            for telem, tval in zip(target, val):
                                locals[telem].append(tval)

        def listcomp_recurse(i, names, data):
            if i == len(names):
                out.append(self.run(node.elt))
                return

            for val in data[i]:
                self.symtable[names[i]] = val
                listcomp_recurse(i+1, names, data)

        names = list(locals.keys())
        data = list(locals.values())

        listcomp_recurse(0, names, data)

        for name, val in saved_syms.items():
            self.symtable[name] = val

        return out

    def on_excepthandler(self, node):  # ('type', 'name', 'body')
        """Exception handler..."""
        return (self.run(node.type), node.name, node.body)

    # if at first you don't succeed... that's what we have except: blocks for...
    def on_try(self, node):    # ('body', 'handlers', 'orelse', 'finalbody')
        """Try/except/else/finally blocks."""

        no_errors = True
        for tnode in node.body:
            # run the body of the try:
            self.run(tnode, with_raise=False)
            no_errors = no_errors and len(self.error) == 0
            # uh oh, there was an exception
            if len(self.error) > 0:
                e_type, e_value, e_tback = self.error[-1].exc_info
                if e_type == None:
                    e_value = self.error_msg

                for hnd in node.handlers:
                    htype = None
                    if hnd.type is not None:
                        htype = builtins.get(hnd.type.id, None)
                    if htype is None or e_type is None or isinstance(e_type(), htype):
                        self.error = []
                        if hnd.name is not None:
                            # put the error string in the 'Exception as' variable
                            self.node_assign(hnd.name, e_value)
                        # run the except: body
                        for tline in hnd.body:
                            self.run(tline)
                        break
                break

        if no_errors and hasattr(node, 'orelse'):
            for tnode in node.orelse:
                self.run(tnode)

        if hasattr(node, 'finalbody'):
            for tnode in node.finalbody:
                self.run(tnode)

    def on_raise(self, node):    # ('type', 'inst', 'tback')
        """Raise an error"""

        excnode = node.exc
        msgnode = node.cause
        lineno = node.lineno

        out = self.run(excnode)
        msg = ' '.join(out.args)

        if msgnode != 'None':
            msg2 = self.run(msgnode)
            if msg2 not in (None, 'None'):
                msg = "%s: %s" % (msg, msg2)

        self.raise_exception(None, exc=out.__class__, msg=msg, expr='', lineno=lineno)

    def on_call(self, node):
        """Function execution."""
        #  ('func', 'args', 'keywords'. Py<3.5 has 'starargs' and 'kwargs' too)

        func = self.run(node.func)
        if not hasattr(func, '__call__') and not isinstance(func, type):
            msg = "'%s' is not callable!!" % (func)
            self.raise_exception(node, exc=TypeError, msg=msg)

        args = [self.run(targ) for targ in node.args]
        starargs = getattr(node, 'starargs', None)
        if starargs is not None:
            args = args + self.run(starargs)

        keywords = {}
        if func == print:
            keywords['file'] = self.writer

        for key in node.keywords:
            if not isinstance(key, ast.keyword):
                msg = "keyword error in function call '%s'" % (func)
                self.raise_exception(node, msg=msg)

            if key.arg is None:
                keywords.update(self.run(key.value))
            elif key.arg in keywords:
                self.raise_exception(node,
                                     msg="keyword argument repeated: %s" % key.arg,
                                     exc=SyntaxError)
            else:
                keywords[key.arg] = self.run(key.value)

        kwargs = getattr(node, 'kwargs', None)
        if kwargs is not None:
            keywords.update(self.run(kwargs))

        if isinstance(func, Procedure):
            self._calldepth += 1

        try:
            out = func(*args, **keywords)
        except Exception as ex:
            out = None
            func_name = getattr(func, '__name__', str(func))
            self.raise_exception(
                node, msg="Error running function call '%s' with args %s and "
                "kwargs %s: %s" % (func_name, args, keywords, ex))
        finally:
            if isinstance(func, Procedure):
                self._calldepth -= 1
        return out


    def on_arg(self, node):    # ('test', 'msg')
        """Arg for function definitions."""
        return node.arg

    def on_functiondef(self, node):
        """Define procedures."""
        global symlock
        # ('name', 'args', 'body', 'decorator_list')
        if node.decorator_list:
            raise Warning("decorated procedures not supported!")
        kwargs = []

        if (not valid_symbol_name(node.name)) or (node.name in self.readonly_symbols):
            errmsg = "invalid function name (reserved word?): '%s'" % (node.name)
            self.raise_exception(node, exc=NameError, msg=errmsg)

        # script-defined functions may not end with _ - that's reserved for
        # functions defined by the framework
        if node.name.endswith('_'):
            errmsg = "invalid function name ('_' ending is reserved): '%s'" % node.name
            self.raise_exception(node, exc=NameError, msg=errmsg)

        offset = len(node.args.args) - len(node.args.defaults)
        for idef, defnode in enumerate(node.args.defaults):
            defval = self.run(defnode)
            keyval = self.run(node.args.args[idef+offset])
            kwargs.append((keyval, defval))

        args = [tnode.arg for tnode in node.args.args[:offset]]

        doc = None
        nb0 = node.body[0]
        if isinstance(nb0, ast.Expr) and isinstance(nb0.value, ast.Str):
            doc = nb0.value.s

        varkws = node.args.kwarg
        vararg = node.args.vararg
        if version_info[0] == 3:
            if isinstance(vararg, ast.arg):
                vararg = vararg.arg
            if isinstance(varkws, ast.arg):
                varkws = varkws.arg

        with symlock:
            self.symtable[node.name] = Procedure(node.name, self, doc=doc,
                                             lineno=self.lineno,
                                             body=node.body,
                                             args=args, kwargs=kwargs,
                                             vararg=vararg, varkws=varkws)

        if node.name in self.no_deepcopy:
            self.no_deepcopy.remove(node.name)

# ----------------------------------------------------------------------------
#
# Procedure class - def functions are evaluated here
#
# ----------------------------------------------------------------------------

class Procedure(object):
    """Procedure - user-defined function for asteval.

    This stores the parsed ast nodes as from the 'functiondef' ast node
    for later evaluation.

    """

    def __init__(self, name, interp, doc=None, lineno=0,
                 body=None, args=None, kwargs=None,
                 vararg=None, varkws=None):
        """TODO: init params."""
        self.__ininit__ = True
        self.name = name
        self.__name__ = self.name
        self.__asteval__ = interp
        self.raise_exc = self.__asteval__.raise_exception
        self.__doc__ = doc
        self.body = body
        self.argnames = args
        self.kwargs = kwargs
        self.vararg = vararg
        self.varkws = varkws
        self.lineno = lineno
        self.__ininit__ = False

        self.lock = RLock()

    def __setattr__(self, attr, val):
        if not getattr(self, '__init__', True):
            self.raise_exc(None, exc=TypeError,
                           msg="procedure is read-only")
        self.__dict__[attr] = val

    def __dir__(self):
        return ['name']

    def __repr__(self):
        """TODO: docstring in magic method."""
        sig = ""
        if len(self.argnames) > 0:
            sig = "%s%s" % (sig, ', '.join(self.argnames))
        if self.vararg is not None:
            sig = "%s, *%s" % (sig, self.vararg)
        if len(self.kwargs) > 0:
            if len(sig) > 0:
                sig = "%s, " % sig
            _kw = ["%s=%s" % (k, v) for k, v in self.kwargs]
            sig = "%s%s" % (sig, ', '.join(_kw))

        if self.varkws is not None:
            sig = "%s, **%s" % (sig, self.varkws)
        sig = "<Procedure %s(%s)>" % (self.name, sig)
        if self.__doc__ is not None:
            sig = "%s\n  %s" % (sig, self.__doc__)
        return sig

    def __call__(self, *args, **kwargs):
        """TODO: docstring in public method."""
        global symlock
        symlocals = {}
        args = list(args)
        nargs = len(args)
        nkws = len(kwargs)
        nargs_expected = len(self.argnames)

        # check for too few arguments, but the correct keyword given
        if (nargs < nargs_expected) and nkws > 0:
            for name in self.argnames[nargs:]:
                if name in kwargs:
                    args.append(kwargs.pop(name))
            nargs = len(args)
            nargs_expected = len(self.argnames)
            nkws = len(kwargs)
        if nargs < nargs_expected:
            msg = "%s() takes at least %i arguments, got %i"
            self.raise_exc(None, exc=TypeError,
                           msg=msg % (self.name, nargs_expected, nargs))
        # check for multiple values for named argument
        if len(self.argnames) > 0 and kwargs is not None:
            msg = "multiple values for keyword argument '%s' in Procedure %s"
            for targ in self.argnames:
                if targ in kwargs:
                    self.raise_exc(None, exc=TypeError,
                                   msg=msg % (targ, self.name),
                                   lineno=self.lineno)

        # check more args given than expected, varargs not given
        if nargs != nargs_expected:
            msg = None
            if nargs < nargs_expected:
                msg = 'not enough arguments for Procedure %s()' % self.name
                msg = '%s (expected %i, got %i)' % (msg, nargs_expected, nargs)
                self.raise_exc(None, exc=TypeError, msg=msg)

        if nargs > nargs_expected and self.vararg is None:
            if nargs - nargs_expected > len(self.kwargs):
                msg = 'too many arguments for %s() expected at most %i, got %i'
                msg = msg % (self.name, len(self.kwargs)+nargs_expected, nargs)
                self.raise_exc(None, exc=TypeError, msg=msg)

            for i, xarg in enumerate(args[nargs_expected:]):
                kw_name = self.kwargs[i][0]
                if kw_name not in kwargs:
                    kwargs[kw_name] = xarg

        # add parameters to local symbol table
        for argname in self.argnames:
            symlocals[argname] = args.pop(0)

        try:
            if self.vararg is not None:
                symlocals[self.vararg] = tuple(args)

            for key, val in self.kwargs:
                if key in kwargs:
                    val = kwargs.pop(key)
                symlocals[key] = val

            if self.varkws is not None:
                symlocals[self.varkws] = kwargs

            elif len(kwargs) > 0:
                msg = 'extra keyword arguments for Procedure %s (%s)'
                msg = msg % (self.name, ','.join(list(kwargs.keys())))
                self.raise_exc(None, msg=msg, exc=TypeError,
                               lineno=self.lineno)

        except (ValueError, LookupError, TypeError,
                NameError, AttributeError):
            msg = 'incorrect arguments for Procedure %s' % self.name
            self.raise_exc(None, msg=msg, lineno=self.lineno)

        shadowpars = {}

        # save any parameters that are already in the global table
        # we restore shadowed vars at the end

        with symlock:
            # for each of the local symbols (function arguments)
            for k in symlocals:
                # if it's in the global symbols already
                if k in self.__asteval__.symtable:
                    # save a copy of the original for later
                    shadowpars[k] = self.__asteval__.symtable[k]

        # add the function arguments to the global table
        try:
            with symlock:
#                save_symtable = self.__asteval__.symtable.copy()
                self.__asteval__.symtable.update(symlocals)
        except Exception as ex:
            if not self.no_print:
                print(ex)

        self.__asteval__.retval = None
        self.__asteval__._calldepth += 1
        retval = None

        # evaluate script of function
        for node in self.body:

            # if node has test instead of value
            if isinstance(node, ast.If) or isinstance(node, ast.While):
                val = node.test
            elif isinstance(node, ast.For):
                val = node.body
            else:
                val = node.value

            if isinstance(val, ast.Call):
                fn = val.func
                exp = fn.id
            else:
                exp = '<>'

            # execute the call
            self.__asteval__.run(node, expr=exp, lineno=self.lineno)

            if len(self.__asteval__.error) > 0:
                if not self.no_print:
                    print(self.__asteval__.error)
            if self.__asteval__.retval is not None:
                retval = self.__asteval__.retval
                self.__asteval__.retval = None
                if retval is ReturnedNone:
                    retval = None
                break

        # restore the global symbols
        with symlock:
            # for anything defined in the proc
            for k in symlocals:
                # if it's not shadowed - must be an argumrnt
                if k not in shadowpars:
                    del self.__asteval__.symtable[k]
            # for each of the saved symbols
            for k in shadowpars:
                # replace the global symbol with the saved original
                self.__asteval__.symtable[k] = shadowpars[k]

        self.__asteval__._calldepth -= 1
        symlocals = None
        return retval

#----------------------------------------------------------------------
#
# Support functions
#
#----------------------------------------------------------------------

#
# print the structure of an object
#
def dump(obj, tag=None):
    print("============================================")
    if tag != None:
        print("", tag)
    else:
        print("")
    if isinstance(obj, dict):
        print (getattr(obj, 'items'))
        for k in obj:
            print ("  {} : {}  {}".format(k, obj[k], type(obj[k])))
    print("=============================================")

#
# print an AST node internals
#
def dumpnode(obj, tag=None):
    print("============================================")
    if tag != None:
        print("", tag)
    else:
        print("")
    for k in obj.__dict__.keys():
        n = obj.__dict__[k]
        print(k, n, type(n))
        if isinstance(n, list):
            for e in n:
                print('    ', e, e.__dict__)
        if isinstance(n, ast.Name):
            print('    ', n, n.__dict__)
        if isinstance(n, ast.List):
            print('    ', n, n.__dict__)
    ast.dump(obj)
    print("=============================================")

