"""
   ApyEngine - An environment for running Python-subset scripts in a relatively
        safe manner.

    This package incorporates "asteval" from https://github.com/newville/asteval

    version: 1.0
    last update: 2023-Nov-13
    License:  MIT
    Author:  Mark Anacker <closecrowd@pm.me>

    Copyright (c) 2023 by Mark Anacker.   All Rights Reserved

"""

from .apyengine import ApyEngine
from .asteval import Interpreter
from .astutils import (NameFinder, valid_symbol_name,
                       make_symbol_table, get_ast_names)
from ._version import get_versions

__all__ = ['AstEngine', 'Interpreter', 'NameFinder', 'valid_symbol_name',
           'make_symbol_table', 'get_ast_names', 'ApyEngine']

__version__ = get_versions()['version']
del get_versions
