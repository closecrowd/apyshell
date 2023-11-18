"""ApyEngine - An interpreter for running Python-subset scripts.

This package contains an interpreter for a safe subset of the
Python3 language.  It does NOT run stand-alone, but must be
imported into a host application.

The companion project "apyshell" demonstrates how to fully use and control
this engine. <https://github.com/closecrowd/apyshell>

Credits:
    * version: 1.0
    * last update: 2023-Nov-17
    * License:  MIT
    * Author:  Mark Anacker <closecrowd@pm.me>
    * Copyright (c) 2023 by Mark Anacker
Note:
    * This package incorporates "asteval" from https://github.com/newville/asteval

"""

from .apyengine import ApyEngine
from .asteval import Interpreter
from .astutils import (NameFinder, valid_symbol_name,
                       make_symbol_table, get_ast_names)
from ._version import get_versions

__all__ = ['ApyEngine', 'Interpreter', 'NameFinder', 'valid_symbol_name',
           'make_symbol_table', 'get_ast_names']

__version__ = get_versions()['version']
del get_versions
