#!/usr/bin/env python3
"""
    extensionmgr - Handles extension load/unload for apyshell

    This script supports the extension handling commands for
    apyshell.

    version: 1.0
    last update: 2023-Nov-13
    License:  MIT
    Author:  Mark Anacker <closecrowd@pm.me>
    Copyright (c) 2023 by Mark Anacker
--------------------------------------------------------------------
"""

import os
import sys
import importlib
import importlib.util

from string import *
from ctypes import *
from types import *

import platform
import threading

from support import *
from extensionapi import *

##############################################################################

#
# Globals
#

# get the current Python version
(pvers, pminor, ppatch) = platform.python_version_tuple()
pver = int(pvers)
pmin = int(pminor)
pverf = float(str(pvers)+'.'+str(pminor))

##############################################################################

MODNAME="extensionmgr:"

# quote the quotes (and newlines)
def quoteSpecial(orig):
    s1 = orig.replace('\n', '\\n')
    s2 = s1.replace("\'", "\\'")
    s1 = s2.replace('\"', '\\"')
    return s1

# ----------------------------------------------------------------------------
#
# Extension Manager class
#
# ----------------------------------------------------------------------------

class ExtensionMgr:

    def __init__(self, eng, epath, options=None):
        debugMsg(MODNAME, "ExtensionMgr")

        self.__engine = eng               # the script engine
        self.__expath = epath             # extension directory path
        if options:
            self.__options = options
        else:
            self.__options = {}

        # if the path is a list, use it
        if type(epath) is list:
            self.__expath = epath
        else:
            # otherwise, try to split it at the ,
            self.__expath = epath.split(',')

        self.__cmddict = {}              # functions we expose to the scripts
        self.__modules = {}               # loaded extension modules
        self.__exobjs = {}                # instances of extension objects
        self.__availExtensions = {}       # available extensions
        self.__activeExtensions = {}      # currently loaded extensions

        self.__cblock = threading.Lock()    # callback lock

        self.__engine.setSysVar_('pythonver', pverf)  # save the Python version

        # create API for the extensions to call back to us
        self.__api = ExtensionAPI(self.__engine, self, True)

    # add our script functions
    def register(self):
        self.__cmddict = {}
        self.__cmddict['scanExtensions_'] = self.scanExtensions_
        self.__cmddict['listExtensions_'] = self.listExtensions_
        self.__cmddict['isExtLoaded_'] = self.isExtLoaded_
        self.__cmddict['loadExtension_'] = self.loadExtension_
        self.__cmddict['unloadExtension_'] = self.unloadExtension_

        self.__engine.addcmds(self.__cmddict)

    # call shutdown() in each active extension
    def shutdown(self):
        for en in self.__activeExtensions.keys():
            ext = self.__activeExtensions[en]
            try:
                ext['obj'].shutdown()
            except:
                pass
        return True

#
# Script-callable API
#

    # return the list of available extension names
    def scanExtensions_(self):
        ''' Return a list[] of available extensions '''
        return self.scanForExtensions(self.__expath, True)

    # return the list of active extension names
    def listExtensions_(self):
        ''' Return a list[] of currently-loaded extensions '''
        # if we have no extensions loaded
        if len(self.__activeExtensions) == 0:
            # force a rescan:
            self.scanForExtensions(self.__expath, True)
        return list(self.__activeExtensions.keys())

    # return True if the named extension is loaded
    def isExtLoaded_(self, ename):
        ''' Return True if an extension is loaded '''
        if not checkFileName(ename):
            return False

        if ename in self.__activeExtensions:
            return True
        return False

    # load a named extension if it's not already loaded
    def loadExtension_(self, ename):
        ''' Load an extension by name (no paths allowed),
        and it has to be available in the extensions directory.
       '''

        # check for an empty
        if not ename or len(ename) < 1:
            return False

        # clean off any paths or other junk
        ename = sanitizePath(ename)

        # check again in case it all went away, or is invalid...
        if not checkFileName(ename):
            return False

        # force a rescan if needed
        if len(self.__availExtensions) == 0:
            self.scanForExtensions(self.__expath, True)

        if ename not in self.__availExtensions:
            debugMsg(MODNAME, "** unknown extension name:", ename)
            return False

        if ename in self.__activeExtensions:
            debugMsg(MODNAME, "** extension already loaded:", ename)
            return False

        (path, mpath) = self.__availExtensions[ename]
        debugMsg(MODNAME, "Loading extension ",ename," from ", path)

        try:

            if pverf > 3.4:
                spec = importlib.util.spec_from_loader(ename, importlib.machinery.SourceFileLoader(ename, path))
                newmod = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = newmod
                spec.loader.exec_module(newmod)
            else:
                debugMsg(MODNAME, 'old module loader')
                oldpath = list(sys.path)
                sys.path.insert(0, mpath)
                try:
                    newmod = __import__(ename)
                finally:
                    sys.path[:] = oldpath # restore the previous path

            try:
                newkey = newmod.__key__
                newclass = newmod.__cname__
            except Exception as e:
                print(str(e))
                # this module is bad - remove it from the list
                del self.__availExtensions[ename]
                return False

            debugMsg(MODNAME, "Loading extension '{}' as '{}'".format(ename, newkey))
            self.__modules[newkey] = newmod

            # get the class
            c = getattr(newmod, newclass)

            # and make an instance of the extension
            m = c(self.__api, self.__options)

            # try to register the extension's functions in the
            # active list
            if m.register():
                self.__activeExtensions[ename] = {'name':ename, 'path':path, 'class':c, 'obj':m}
            else:
                errorMsg(MODNAME, 'Extension',ename,'failed to load')
                return False

            self.__exobjs[ename] = m

            return True
        except Exception as e:
            errorMsg(MODNAME, '*** Extension load error:'+str(e))

        return False


    def unloadExtension_(self, ename):
        ''' Remove a currently-loaded extension '''

        if not checkFileName(ename):
            return False

        if ename not in self.__availExtensions:
            debugMsg(MODNAME, "** unknown extension name:", ename)
            return False

        # if it's an active extension
        if ename in self.__exobjs:
            # get the current instance
            m = self.__exobjs[ename]
            # shut it down
            m.shutdown()
            # and remove the commands
            m.unregister()

            # remove the module and instance from the tables
            del self.__exobjs[ename]
            del self.__modules[ename]
            del self.__activeExtensions[ename]

        return True

#
# event handler callback
#

    # event callbacks from extensions come here
    # they are then dispatched into the script
    def handleEvents(self, name, data):
        # if not data or not name:
        if not name or len(name) < 1:
            return None

        # lookup the handler for this event

        # or this - not found in the engine
        if not self.__engine.isDef_(name):
            return None

        # create the command string
        if data != None:
            cmd = name+"("+str(data)+")"
        else:
            cmd = name+"()"

        # and call the engine to run it
        ret = None
        try:
            ret = self.__engine.eval_(cmd)
        except Exception as e:
            print(str(e))

        return ret


#
# Support methods
#

    # build the list of (path, extension)
    # and save the internal flag
    def scanForExtensions(self, dir, iflag):
        sext = '.py'

        # if it's a list, use it
        if type(dir) is list:
            self.spath = dir
        else:
            self.spath = [dir]

        # for each path in the list
        for pl in self.spath:
            # get the entries
            dl = [(pl,x.split('.')[0]) for x in os.listdir(pl) if x.endswith(sext)]
            if len(dl) > 0:
                # add to the extension directory list
                # for each filename
                for de in dl:
                    (mpath, pname) = de

                    # skip the module flag
                    if pname == '__init__':
                        continue

                    filename = mpath+'/'+pname+sext
                    # add to the set of available exts keyed by name
                    self.__availExtensions[de[1]] = (filename, mpath)
        debugMsg(MODNAME, "scan:", self.__availExtensions)

        return list(self.__availExtensions.keys())



