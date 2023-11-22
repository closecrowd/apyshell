#!/usr/bin/env python3
"""fileext - file handling extension.

This extension provides some simple text file handling.  It
limits the file locations to a pre-set root directory.

Make these functions available to a script by adding:

    loadExtension_('fileext')

to it.  Functions exported by this extension:

Methods:
    readLines_()    :   read a text file line-by-line or all-at-once
    writeLines_()   :   write a line (or lines) to a text file,
                        creating the file if need be. *
    appendLines_()  :   write a line (or lines) to the end of a text
                        file, extending it. *
    listFiles_()    :   return a list of files in the given path *

* may be disabled by option settings

Credits:
    * version: 1.0
    * last update: 2023-Nov-13
    * License:  MIT
    * Author:  Mark Anacker <closecrowd@pm.me>
    * Copyright (c) 2023 by Mark Anacker

"""

modready = True

import os

from support import *
from extensionapi import *

##############################################################################

#
# Globals
#

__key__ = 'fileext'
__cname__ = 'FileExt'

MODNAME = "fileext"

##############################################################################

# ----------------------------------------------------------------------------
#
# Extension class
#
# ----------------------------------------------------------------------------

class FileExt():
    """This class manages commands to read and write files."""

    def __init__(self, api, options={}):
        """Constructs an instance of the FileExt class.

        This instance will manage all named queues.  There will be only
        one of these instances at a time.

        Args:
            api     : an instance of ExtensionAPI connecting us to the engine

            options : a dict of option settings passed down to the extension

        Options:
                    'file_root' - a path prepended to all
                                filenames, restricting access to files
                                below this point.

                    'read_only' = If True,  the writeLines_ and
                              appendLines_ commands are not installed.

                    'list_dirs' - If True, allows the list_dirs_ call

        """

        self.__api = api
        self.__options = options
        self.__cmddict = {}

        if options:
            self.__fileroot = options.get('file_root', None)
            self.__readonly = options.get('read_only', False)
            self.__listdirs = options.get('list_dirs', True)
        else:
            self.__fileroot = None
            self.__readonly = False
            self.__listdirs = True

    def register(self):
        """Make this extension's functions available to scripts

        This method installs our script API methods as functions in the
        engine symbol table, making them available to scripts.

        This is called by the ExtensionMgr during loading.

        Note:
            Functions installed:
                * readLines_()    :   read a text file line-by-line or all-at-once
                * writeLines_()   :   write a line (or lines) to a text file,
                                        creating the file if need be.
                * appendLines_()  :   write a line (or lines) to the end of a text
                                        file, extending it.
                * listFiles_()    :   return a list of files in the given path

        Args:
            None

        Returns
            True        :   Commands are installed and the extension is
                            ready to use.

            False       :   Commands are NOT installed, and the extension
                            is inactive.

        """

        if not modready:
            return False

        self.__cmddict['readLines_'] = self.readLines_
        if not self.__readonly:
            self.__cmddict['writeLines_'] = self.writeLines_
            self.__cmddict['appendLines_'] = self.appendLines_
        if self.__listdirs:
            self.__cmddict['listFiles_'] = self.listFiles_

        # register the extensions script functions
        self.__api.registerCmds(self.__cmddict)

        return True

    def unregister(self):
        ''' Remove this extension's commands '''
        if not modready:
            return False

        # unregister the extensions script functions
        self.__api.unregisterCmds(self.__cmddict)

        return True

    def shutdown(self):
        ''' Perform a graceful shutdown '''
        return True

#----------------------------------------------------------------------
#
# Script API
#
#----------------------------------------------------------------------

#
# Simple text file functions
#

    def readLines_(self, filepath, handler=None, maxlines=0):
        """Read data from a file in text mode.

        Read a text file all-at-once, or line by line.

            Args:
                filepath    :   filename (and optional path) to read from.
                                Absolute (/) and parent (..) paths are not
                                allowed.  Path will be under "file_root" if
                                configured.  Required.

                handler     :   The name of a script function that wll be
                                called with every line of text.  The
                                function will be called with a single str
                                parameter containing the text line.  If the
                                handler returns False, file reading is stopped.
                                Optional.

                maxlines    :   The number of lines to read before stopping.  If
                                omitted or 0, read until the end of the file.  Optional.

            Returns:
                None            :   If there was an error opening the file

                data            :   str     The lines from the file if no handler
                                            was specified

                count           :   int     The number of lines sent to the handler

        """

        fp = sanitizePath(filepath)
        if not fp:
            return None

        # add a root path prefix if configured
        if self.__fileroot:
            fp = self.__fileroot+'/'+fp

        try:
            # no handler
            if not handler:
                # slurp it all in at once - mind the memory
                with open(fp,  'r') as f:
                    data = f.read()
                return data
            else:
                cnt = 0
                with open(fp,  'r') as f:
                    cnt = 0
                    for line in f:
                        # call the script handler to process the line
                        rv = self.__api.handleEvents(handler, '"'+line.strip()+'"')
                        cnt += 1
                        if maxlines > 0 and cnt >= maxlines or rv == False:
                            break
                return cnt
        except Exception as ex:
            return retError(self.__api, MODNAME, 'Error reading file "'+filepath+'":'+str(ex), None)
        return None


    def writeLines_(self, filepath, data, handler=None, maxlines=0):
        """Write lines of data to a text file, overwriting any previous file

        Write to a text file all-at-once, or line by line.

            Args:
                filepath    :   filename (and optional path) to read from.
                                Absolute (/) and parent (..) paths are not
                                allowed.  Path will be under "file_root" if
                                configured.  Required.

                data        :   A string to write to the file as a line of text,
                                or a list[] of strings that will be written as
                                multiple lines.  Required.

                handler     :   The name of a script function that wll be
                                called to obtain a line of text to be
                                written to the file. If the handler returns
                                False, file writing is stopped.  Optional.

                maxlines    :   The number of lines to write before stopping.  If
                                omitted or 0, write until the data is exhausted.
                                Optional.

            Returns:
                None    :   If there was an error opening the file

                count   :   int     The number of lines sent to the
                                    handler, or the number of bytes sent if
                                    no handler.

        """

        fp = sanitizePath(filepath)
        if not fp:
            return None

        # add a root path prefix if configured
        if self.fileroot:
            fp = self.__fileroot+'/'+fp

        return lineWriter(self.__api,  fp, data, handler=handler, maxlines=maxlines, mode='w')


    def appendLines_(self, filepath, data, handler=None, maxlines=0):
        """Write lines of data to a text file, appending to any previous file

        Append lines to a text file all-at-once, or line by line.

            Args:
                filepath    :   filename (and optional path) to read from.
                                Absolute (/) and parent (..) paths are not
                                allowed.  Path will be under "file_root" if
                                configured.  Required.

                data        :   A string to write to the file as a line of text,
                                or a list[] of strings that will be written as
                                multiple lines.  Required.

                handler     :   The name of a script function that wll be
                                called to obtain a line of text to be
                                written to the file. If the handler returns
                                False, file writing is stopped.  Optional.

                maxlines    :   The number of lines to write before stopping.  If
                                omitted or 0, write until the data is exhausted.
                                Optional.

            Returns:
                None    :   If there was an error writing to the file

                count   :   int     The number of lines sent to the
                                    handler, or the number of bytes sent if
                                    no handler.

        """

        fp = sanitizePath(filepath)
        if not fp:
            return None

        # add a root path prefix if configured
        if self.__fileroot:
            fp = self.fileroot+'/'+fp

        return lineWriter(self.__api,  fp, data, handler=handler, maxlines=maxlines, mode='a')

    def listFiles_(self, filepath=''):
        """return a list of files """

        fp = sanitizePath(filepath)

        # add a root path prefix if configured
        if self.__fileroot:
            if fp:
                fp = self.__fileroot+'/'+fp
            else:
                fp = self.__fileroot
        else:
            fp = '.'

        print(fp)

        flist = os.listdir(fp)
        return flist



#----------------------------------------------------------------------
#
# Support functions
#
#----------------------------------------------------------------------

# write data depending on it's type
def typeWrite(f,  data):

    if not data:
        return None

    cnt = 0

    if type(data) is str:
        c = f.write(str(data))
        return c
    if type(data) is list:
        for line in data:
            c = f.write(str(line)+'\n')
            cnt += c
        return cnt

# TODO: add dict support

    return None


def lineWriter(api,  fp, data, handler=None, maxlines=0,  mode='w'):
    ''' Write lines to a file in either overwite or append mode

        Parameters
        ----------

        fp
        data
        handler
        maxlines
        mode
        Returns
        -------

    '''
    try:
        if not handler:
            with open(fp,  mode) as f:
                c = typeWrite(f, data)
            return c
        else:
            # calling a handler for the data
            cnt = 0
            with open(fp,  mode) as f:
                while True:
                    line = api.handleEvents(handler, ' ')
                    if not line:
                        break
                    c = typeWrite(f, line)
                    cnt += 1
                    if maxlines > 0 and cnt >= maxlines:
                        break
            return cnt
    except Exception as ex:
        return retError(api, MODNAME, 'Error writing file "'+filepath+'":'+str(ex), None)
    return None

