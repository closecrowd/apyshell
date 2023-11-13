#!/usr/bin/env python3
"""
    support - Various stand-alone support functions for apyshell

    version: 1.0
    last update: 2023-Nov-13
    License:  MIT
    Author:  Mark Anacker <closecrowd@pm.me>
    Copyright (c) 2023 by Mark Anacker
--------------------------------------------------------------------
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
#debug = True

##############################################################################

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
    if not fname or len(fname) < 1:
        return False

    return all(char in VALIDCHARS for char in fname)

# clean off unwanted path elements
# Linux-specific for now
def sanitizePath(path):
    if not path or len(path) < 1:
        return None

    #
    # Linux path sanitation
    #

    # strip out \\
    while path and '\\' in path:
        path = path.replace('\\',  '')
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
    # Windows - TODO
    #

    return path

# log an error and return
def retError(api, module, msg, ret=None):
    if api != None:
        api.logError(module, msg)
    else:
        print(module, msg)
    if ret:
        return ret
    return False

# unlock a thread lock
def unlock__(lock):
    if lock:
        if lock.locked():
            lock.release()

# return a dict entry or default, optionally remove it
def getparam(table, key, default, remove=False):
    if key in table:
        ret = table[key]
        if remove:
            del table[key]
    else:
        ret = default
    return ret

# set or replace a value in a dict
def setparam(table, key, value, replace=False):
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
    # already present
    if oldkey in table:
        # if we don't have a new value
        if value == None:
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
        try:
            ret = q.get(True, timeout)   # blocking
            return ret
        except:
            return defvalue

