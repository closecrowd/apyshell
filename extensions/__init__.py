""" Extensions - Add additional functionality to scripts.

This package contains modules that add special fuctions to apyshell.
Scripts can use the loadExtension_() command to add any of these modules
that are in the extensionsdir directory, and make their commands
available to the scripts.  Extensions may be unloaded as well.33

Credits:
    * version: 1.0.0
    * last update: 2023-Nov-17
    * License:  MIT
    * Author:  Mark Anacker <closecrowd@pm.me>
    * Copyright (c) 2023 by Mark Anacker

"""

__all__ = [ 'fileext', 'mqttext', 'queueext' , 'redisext',
            'sqliteext', 'utilext' ]
