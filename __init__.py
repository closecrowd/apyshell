""" ApyShell - Python Embedded apy script runnner

This package creates a framework for running lightweight scripts under
the apyengine interpreter.  It demonstrates embedding and controlling
the engine.  It can be run either stand-alone, or itself embedded into
an application.

The companion project "apyengine" has documentation and examples of
how to use the apyengine outside of this package.  The entire
apyengine package is included in this package for convenience.
<https://github.com/closecrowd/apyengine>

Credits:
    * version: 1.0.0
    * last update: 2024-Jan-05
    * License:  MIT
    * Author:  Mark Anacker <closecrowd@pm.me>
    * Copyright (c) 2023,2024 by Mark Anacker

"""

from apyengine.apyengine import *
from .extensionmgr import *
from .support import *

__all__ = ['apyshell', 'extensionmgr', 'extensionapi', 'support', 'apyengine']
