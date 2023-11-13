#!/usr/bin/env python3
"""
    ApyEngine - An environment for running Python-subset scripts in a relatively
        safe manner.

    This package incorporates "asteval" from https://github.com/newville/asteval

    version: 1.0
    last update: 2023-Nov-13
    License:  MIT
    Author:  Mark Anacker <closecrowd@pm.me>
    Copyright (c) 2023 by Mark Anacker
-----------------------------------------------------------------
"""

import sys
from types import *
from os.path import exists

import gc

from .asteval import Interpreter
from .astutils import valid_symbol_name

##############################################################################

#
# Globals
#

DEFAULT_EXT = '.apy'

##############################################################################


# ----------------------------------------------------------------------------
#
# Engine class
#
# ----------------------------------------------------------------------------

class ApyEngine():
    """
        Create an instance of the AstEngine script runner.

            Args:
                basepath            The top directory where script files will be found. Relative paths below this
                                    point are allowed.
                builtins_readonly   If True, protect the built-in symbols from being overridden (default)
                global_funcs        If True, all variables are global, even in def functions.
                                    If False, vars created in a def func are local to that func (default)
                                    Can also be modified by setSysFlags_()
                writer              The output stream for normal print() output. Defauls to stdout
                err_writer          The output stream for errors. Defaults to stderr
    """
    def __init__(self, basepath=None, builtins_readonly=True, global_funcs=False, writer=None,
                 err_writer=None):

        self.__writer = writer or sys.stdout
        self.__err_writer = err_writer or sys.stderr

        self.__usersyms = {}
        self.__persistprocs = []
        self.__systemVars = {}
        # list of installs
        self.__installs = []


        # load the interpreter
        self.__ast = Interpreter(writer=writer, err_writer=err_writer,
                            builtins_readonly=builtins_readonly, global_funcs=global_funcs)

        if sys.platform.startswith('win'):
            self.__windows = True
        else:
            self.__windows = False

        # if no base path for the scripts was given, use the current directory
        if basepath == None or len(basepath) == 0:
            if self.__windows:
                self.__basepath = []
            else:
                self.__basepath = ['./']
        else:
            if type(basepath) is list:
                self.__basepath = basepath
            else:
                self.__basepath = basepath.split(',')

        self.__abort = False
        self.__lastScript = ''    # name of the most-recent script

        # register these methods as script-callable funcs
        self.regcmd("setSysFlags_", self.setSysFlags_)
        self.regcmd("getSysFlags_", self.getSysFlags_)
        self.regcmd("eval_", self.eval_)
        self.regcmd("check_", self.check_)
        self.regcmd("getSysVar_", self.getSysVar_)
        self.regcmd("install_", self.install_)
        self.regcmd("listModules_", self.list_Modules_)
        self.regcmd("loadScript_", self.loadScript_)
        self.regcmd("isDef_", self.isDef_)
        self.regcmd("listDefs_", self.listDefs_)
        self.regcmd("getvar_", self.getvar_)
        self.regcmd("setvar_", self.setvar_)
        self.regcmd("exit_", self.exit_)

    def dumpst(self, tag=None):
        dump(self.__ast.symtable, tag)

    def dumpus(self):
        dump(self.__usersyms)

    def reporterr(self, msg):
        """ print error messages on the console stderr """
        print("!!! "+msg, file=self.__err_writer)
        return msg

#
# engine API
#

    # not currently implemented
    def setSysFlags_(self, flagname,  state):
        if not self.__ast:
            return False

        if state not in { True,  False }:
            return False;

        return False

    # not currently implemented
    def getSysFlags_(self, flagname):
        if not self.__ast:
            return False

        return False

    # stop the script ASAP
    def abortrun(self):
        if self.__ast:
            self.__abort = True
            try:
                self.__ast.abortrun()
            except Exception as e:
                print("abort error:"+str(e))

    # add a new command
    def regcmd(self, name, func=None):
        """ register a new command for the scripts to use """
        if not name or len(name) < 1:
            return False
        # if it's a valid name
        if valid_symbol_name(name):
            # and has a function body
            if func != None:
                # add or replace in the table
                self.__ast.addSymbol(name, func)
                # and add the name to the RO table if it isn't already
                if name not in self.__ast.readonly_symbols:
                    self.__ast.readonly_symbols.add(name)
                return True
        return False

    # remove a registered command
    def unregcmd(self, name):
        """ unregister a command """
        if not name:
            return False
        # if it's a valid name
        if asteval.valid_symbol_name(name):
            self.__ast.delSymbol(name)
            if name in self.__ast.readonly_symbols:   # set
                self.__ast.readonly_symbols.remove(name)
            return True
        return False

    # add new built-in commands after init
    def addcmds(self, cmddict, value=None):
        """ register a whole dict of new commands for the scripts to use """
        if cmddict != None:
            if type(cmddict) is dict:
                for k, v in cmddict.items():
                    self.regcmd(k, v)
            if type(cmddict) is str:
                if value != None:
                     self.regcmd(cmddict,  value)

    def delcmds(self, cmddict, value=None):
        """ register a whole dict of new commands for the scripts to use """
        if cmddict != None:
            if type(cmddict) is dict:
                for k, v in cmddict.items():
                    self.unregcmd(k)
            if type(cmddict) is str:
                if value != None:
                     self.unregcmd(cmddict)

#
# script proc persistence
#

    # add or remove the proc from the persist list
    # if flag == True, make sure it's on the persist list
    #     if False, make sure it's not
    def setProcPersist(self, pname, flag):
        """ add or remove the proc from the persist list
                if flag == True, make sure it's on the persist list
                if False, make sure it's not
        """
        # setting persist state
        if flag == True:
            # already in there?
            if pname in self.__persistprocs:
                return True
            else:
                self.__persistprocs.append(pname)
                return True
        # resetting the state
        else:
            # already in there?
            if pname in self.__persistprocs:
                # remove it
                try:
                    pindex = self.__persistprocs.index(pname)
                    del self.__persistprocs[pindex]
                except:
                    pass
                return True
        return False

    # remove a specified proc from the engine (and the persist list if needed)
    def delProc(self, pname):
        """ remove a specified proc from the engine (and the persist list if needed) """
        if pname in self.__ast.symtable:
            if type(self.__ast.symtable[pname]) == asteval.asteval.Procedure:
                # and take it out of the symbol table
                self.__ast.delSymbol(pname)
                # is this a persistent one?
                if pname in self.__persistprocs:
                    try:
                        pindex = self.__persistprocs.index(pname)
                        del self.__persistprocs[pindex]
                    except:
                        pass
                    return True
        return False

    # remove all currently-defined def functions
    # *except* those on the exception_list
    def clearProcs(self, exception_list=None):
        """ remove all currently-defined def functions
            *except* those on the exception_list """
        klist = []

        for k in self.__ast.symtable:
            if type(self.__ast.symtable[k]) == asteval.asteval.Procedure:
                # skip the persistent ones
                if k not in self.__persistprocs:
                    klist.append(k)

        # did we find any?
        if len(klist) < 1:
            return

        for k in klist:
            # if we have an exception list
            if exception_list != None:
                # and this proc is on it
                if k in exception_list:
                    # don't remove
                    continue
            # and take it out of the symbol table
            self.__ast.delSymbol(k)
        # clean up the heap
        gc.collect()

#
# Script-callable functions
#
    # directly execute a script statement
    def eval_(self, cmd):
        """ directly execute a script statement in the engine """

        if not cmd:
            return None

        rv = None
        try:
            rv = self.__ast.eval(cmd)
        except Exception as e:
            print("eval error:"+str(e))
            return self.reporterr("Error in command: "+str(e))
        return rv

    # syntax check an expression
    def check_(self, code):
        """ syntax check an expression """
        if not code:
            return None
        try:
            self.__ast.parse(code)
            return 'OK'
        except Exception as e:
            return self.reporterr("Error in code: "+str(e))

    # set a value in the system dict
    def setSysVar_(self, name, val):
        if not name:
            return False
        try:
            # don't allow replacing the entire table
            if name == '_sysvars_':
                return False
            self.__systemVars[name] = val
            # save a list of the symbols in a script-accessible variable
            self.__systemVars['_sysvars_'] = list(self.__systemVars.keys())
            return True
        except:
            return False

    # install a pre-authorized Python module into the engine's symbol table
    def install_(self, modname):
        """ install a pre-authorized Python module into the engine's symbol table """
        if not modname:
            return False

        # if we haven't installed it already
        if modname not in self.__installs:
            # if the module installed
            if self.__ast.install(modname):
                # add it to our local list
                self.__installs.append(modname)
                return True
        return False

    # return the list of installed modules
    def list_Modules_(self):
        return self.__installs

    # load and execute a script file
    def loadScript_(self, filename, persist=False):
        """ load and execute a script file """
        if not filename:
            return self.reporterr("Error loading script - Missing filename")

        # verify the file name
        # no quoting (*nix systems only)
        # clean up the submitted fiename
        sfilename = sanitizePath(filename)
        if len(sfilename) < 1:
            return self.reporterr("Error loading script '"+filename+"': Invalid filename")
        filename = sfilename

        # add the extension if needed
        if filename[-4:] != DEFAULT_EXT:
            filename += DEFAULT_EXT

        # find the file on the script path(s)
        fn = findFile(self.__basepath, filename)
        if not fn:
            return self.reporterr("Error - unknown script '"+filename+'"')

        try:
            # add the extension if needed
            if fn[-4:] != DEFAULT_EXT:
                fn += DEFAULT_EXT

            # load the script
            infile = open(fn ,'r')
            # read a line - TODO: add a check for early exit here (maybe)
            scode = infile.read()
            infile.close()

            ccode = self.__ast.parse(scode)

            # save the current script name
            self.__lastScript = filename
            self.setSysVar_('currentScript', filename)

            # and run the code
            self.__ast.run(ccode)
            if persist:
                newprocs = self.getProcs_()
                if len(newprocs) > 0:
                    for k in newprocs:
                        self.__persistprocs.append(k)

        except Exception as e:
            es = ""
            for e in self.__ast.error:
                t =  e.get_error()
                if t != None:
                    es = str(t[0]) + ": " + str(e.msg)
                else:
                    es = e.msg
                break

            return self.reporterr("Error loading script '"+filename+"': "+es)

        return None

    # is a script symbol defined?
    def isDef_(self, name):
        """ return True if the symbol is defined """
        if not name:
            return False
        # strip off () if it's a proc
        lp = name.find('(')
        if lp >= 0:
            # get the bare symbol name
            key = name[0:lp]
        else:
            key = name

        if key in self.__ast.symtable:
            return True
        return False

    # returns a list of currently-defined def functions
    def listDefs_(self, exception_list=None):
        """ returns a list of currently-defined def functions """
        klist = []
        for k in self.__ast.symtable:
            if type(self.__ast.symtable[k]) == asteval.asteval.Procedure:
                klist.append(k)
        return klist

    # return a system var to the script (read-only to scripts)
    def getSysVar_(self, name, default=None):
        if not name:
            return default
        try:
            if name not in self.__systemVars:
                return default
            else:
                return self.__systemVars[name]
        except:
            return default

    # returns the value of a script variable to the outer program
    def getvar_(self, vname, default=None):
        """ returns the value of a script variable to the outer program """
        if not vname:
            return default

        ret = self.__ast.getSymbol(vname)
        if not ret:
            return default

        return ret

    # set a script variable from the outside
    # pass None as val to delete
    def setvar_(self, vname, val):
        """ set a variable from the outside
            pass None as val to delete the variable"""
        if not vname or len(vname) < 1:
            return False
        # if it's a valid name
        if asteval.valid_symbol_name(vname):
            # don't change read-only vars
            if self.__ast.isReadOnly(vname):
                return False
            # if we pass something
            if val != None:
                # add it to the table
                self.__ast.addSymbol(vname,  val)
                return True
            else:
                # otherwise, del any existing copy
                self.__ast.delSymbol(vname)
                return True
        return False

    # exit the engine
    def exit_(self, ret):
        sys.exit(ret)

#----------------------------------------------------------------------
#
# Support functions
#
#----------------------------------------------------------------------

# scan a list of dirs looking for a file
# used by loadScript_()
def findFile(paths, filename):
    if not paths or not filename:
        return None
    if len(paths) == 0 or len(filename) == 0:
        return None

    for dir in paths:
        fn = dir+'/'+filename
        if exists(fn):
            return fn

    return None

# sanitize a file path
def sanitizePath(path):
    if not path:
        return ''

    while '\\' in path and path:
        path = path.replace('\\',  '')
    while '..' in path and path:
        path = path.replace('..', '')
    while '//' in path and path:
        path = path.replace('//', '/')
    # leading dirs are not allowed
    while path and path[0] == '/':
        path = path[1:]

    return path

def dump(obj, tag=None):
    print("============================================")
    if tag != None:
        print("", tag)
    else:
        print("")
    if type(obj) is DictType:
        print(getattr(obj, 'items'))
        for k in obj:
            if type(obj[k]) == asteval.asteval.Procedure:
                print("  {} : {}  {}".format(k, obj[k], type(obj[k])))
    print("=============================================")

