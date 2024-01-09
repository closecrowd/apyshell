#!/usr/bin/env python3
"""support - Various stand-alone support functions for apyshell.

This file contains various utility functions used by apyshell.

Credits:
    * version: 1.0.0
    * last update: 2024-Jan-05
    * License:  MIT
    * Author:  Mark Anacker <closecrowd@pm.me>
    * Copyright (c) 2023,2024 by Mark Anacker

"""

import sys
import os
import string

##############################################################################

#
# Globals
#

# chars we allow in file names (or other user-supplied names)
# a-zA-Z0-9_-
VALIDCHARS = string.ascii_letters+string.digits+'_-'

debug = False
# debug = True

##############################################################################

# print('support')

def enableDebug(arg):
    global debug
    if arg:
        debug = True

def debugMsg(source='', *args):
    global debug

    if debug:
        print(source+":", *args, file=sys.stderr)


def errorMsg(source='', *args):
    print('!!!('+source+'):', *args, file=sys.stderr)

#
# return True if the string contains only a-zA-Z0-9-_
# Used as a valid string check on script-supplied file names
def checkFileName(fname):
    """Check a file name

    Checks the given filename for characters in the set
    of a-z, A-Z, _ or -

        Args:
            fname   :   The name to check
        Returns:
            True if the name is entirely in that set
            False if there were invalid char(s)

    """

    if not fname or len(fname) < 1 or len(fname) > 256:
        return False

    return all(char in VALIDCHARS for char in fname)

# clean off unwanted path elements
# Linux-specific for now
def sanitizePath(path):
    """Clean a path.

    Remove dangerous characters from a path string.

        Args:

            path    :   The string with the path to clean

        Returns:

            The cleaned path or None if there was a problem

    """

    if not path or len(path) < 1 or len(path) > 4096:
        return None

    #
    # Linux path sanitation
    #

    # strip out \\
    while path and '\\' in path:
        path = path.replace('\\',  '')
    # strip out ..
    while path and '..' in path:
        path = path.replace('..',  '')
    # strip out |
    while path and '|' in path:
        path = path.replace('|',  '')
    while path and ':' in path:
        path = path.replace(':',  '')
    while path[0] == '/':
        path = path[1:]

    np = os.path.normpath(path)
    (p, f) = os.path.split(np)

    path = os.path.join(p, f)


    #
    # Windows - TODO:
    #

    return path

# log an error and return
def retError(api, module, msg, ret=False):
    """Logging error return.

    Extensions call this function to log an error message through
    the ExtensionMgr API, then pass up an error value.

        Args:

            api     :   The extensionmgr api reference.

            module  :   A string with the failed module name.

            msg     :   The actual error message.

            ret     :   The value to return.

        Returns:

            The value of ret, or False if it's missing.

    """

    if api is not None:
        api.logError(module, msg)
    else:
        print(module, msg)
    # if the return is None, return that
    if not ret:
        return None
    # otherwise, return the True/False value
    return ret

# unlock a thread lock
def unlock__(lock):
    """Unlock a locked mutex.

    Utility function to unlock a mutex if it's currently
    locked.

        Args:

            lock    :   An instance of threading.Lock().

        Returns:

            Nothing.

    """

    if lock:
        if lock.locked():
            lock.release()

# return a dict entry or default, optionally remove it
def getparam(table, key, default, remove=False):
    """Destructively return a dict entry.

    Return a value from a dict, optionally removing it from the
    dict after grabbing it.  This is mainly used to remove options
    from a **kwargs parameter before passing it down to a lower
    level function.

    If the key is not found in the dict, return a default value.  Remove
    has no effect in this case.

        Args:

            table   :   The dict object to modify.

            key     :   The key to look up.

            default :   A default value to return if key isn't found.

            remove  :   If True, remove the entry if found.

        Returns:

            The value from the dict, or the default.

    """
    if key in table:
        ret = table[key]
        if remove:
            del table[key]
    else:
        ret = default
    return ret

# set or replace a value in a dict
def setparam(table, key, value, replace=False):
    """Add or update a value in a dict.

    This function adds a value to a dict, or optionally replaces
    an existing value.  This is mainly used to manipulate values
    in **kwargs parameters.

    If the key is not found in the table, add it and it's value.
    Replace has no effect in this case.

        Args:

            table   :   The dict object to modify.

            key     :   The key to look up.

            value   :   The value to add or replace

            replace :   If True, update an existing value if found.

        Returns:

            Nothing.

    """

    # already present
    if key in table:
        # and we're replacing it
        if replace:
            table[key] = value
    else:
        # it's not already there:
        table[key] = value

# swap keys, or create a new entry
def swapparam(table, oldkey, newkey, value=None):
    """Move a dict entry to a new key.

    This function will move a dict entry from an old key to a new
    key, optionally replacing the value at the same time.  If the
    old key doesn't exist, a new entry is created.

    """

    # already present
    if oldkey in table:
        # if we don't have a new value
        if value is None:
            # just swap keys
            table[newkey] = table[oldkey]
        else:
            # otherwise, create a new entry
            table[newkey] = value
        # remove the old entry
        del table[oldkey]
    else:
        # it's not already there:
        table[newkey] = value

# get the next item from a queue, or a default value
def get_queue(q, defvalue=None, timeout=0):
    """Get the next value from a Queue.

    This function does a blocking GET from a Queue, returning the
    next item.  If the timeout is > 0 and expires, or there was an
    error on the get(), return a default value.

    """

    try:
        ret = q.get(True, timeout)   # blocking
        return ret
    except:
        return defvalue
