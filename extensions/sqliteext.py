#!/usr/bin/env python3
"""
    sqliteext - SQlite3 database functions

    This extension allows a script to store and retrieve data from a
    sqlite3 database.  The database files are stored under a directory
    passed in via the "sql_root" option.

    Some basic knowledge of SqLite3 and SQL is helpful when using this
    extension.

    All functions are mutex-protected, and can be used from multiple threads.

    Make the functions available to a script by adding:

        loadExtension_('sqliteext')

    to it.  Functions exported by this extension:

            sql_open_()         :   Open a sqlite3 database, creating it if it
                                    doesn't exist.
            sql_close_()        :   Close an open connection.
            sql_execute_()      :   Execute a SQL command in the open database.
            sql_commit_()       :   Commit any pending transactions (in autocommit == False)
            sql_rollback_()     :   Roll back any pending transactions
            sql_changes_()      :   Return the number of rows recently altered
            sql_cursor_fetch_() :   Return rows from a cursor after an execute_()
            sql_list_()         :   Return a list[] of the active connection names

    Required Python modules:

        sqlite3

    version: 1.0
    last update: 2023-Nov-13
    License:  MIT
    Author:  Mark Anacker <closecrowd@pm.me>
    Copyright (c) 2023 by Mark Anacker
--------------------------------------------------------------------
"""


modready = True
try:
    import sqlite3
except Exception as ex:
    modready = False
    print('import failed:', ex)

import threading

from support import *
from extensionapi import *

##############################################################################

#
# Globals
#

__key__ = 'sqliteext'
__cname__ = 'SqLiteExt'

MODNAME = "sqliteext"

##############################################################################


# ----------------------------------------------------------------------------
#
# Extension class
#
# ----------------------------------------------------------------------------

class SqLiteExt():

    ''' This class manages commands to use a sqlite3 database. '''

    def __init__(self, api, options={}):
        '''
        Parameters
        ----------
        api     : an instance of ExtensionAPI connecting us to the engine
        options : a dict of option settings passed down to the extension

            Defined options:    'sql_root' - a path prepended to all
                                database names, restricting access to
                                db files below this point.

                                'sql_ext' - filename extension to use for
                                database files.  Defaults to '.db'
        '''

        self.__api = api
        self.__options = options
        self.__cmddict = {}

        if options:
            self.sqlroot = options.get('sql_root', None)
            self.sqlext = options.get('sql_ext', 'db')
        else:
            self.sqlroot = None
            self.sqlext = 'db'

        self.__conns = {} # sqlite3 database objects

        self.__locktimeout = 5
        self.__lock = threading.Lock()

    def register(self):
        ''' Make this extension's commands available to scripts

        Commands installed
        ------------------

            sql_open_()         :   Open a sqlite3 database, creating it if it
                                    doesn't exist.
            sql_close_()        :   Close an open connection.
            sql_execute_()      :   Execute a SQL command in the open database.
            sql_commit_()       :   Commit any pending transactions (in autocommit == False)
            sql_rollback_()     :   Roll back any pending transactions
            sql_changes_()      :   Return the number of rows recently altered
            sql_cursor_fetch_() :   Return rows from a cursor after an execute_()
            sql_list_()         :   Return a list[] of the active connection names

        Returns
        -------
        True            :   Commands are installed and the extension is
                            ready to use.
        False           :   Commands are NOT installed, and the extension
                            is inactive.
        '''

        if not modready:
            return False

        self.__cmddict['sql_open_'] = self.sql_open_
        self.__cmddict['sql_close_'] = self.sql_close_
        self.__cmddict['sql_execute_'] = self.sql_execute_
        self.__cmddict['sql_commit_'] = self.sql_commit_
        self.__cmddict['sql_rollback_'] = self.sql_rollback_
        self.__cmddict['sql_changes_'] = self.sql_changes_
        self.__cmddict['sql_cursor_fetch_'] = self.sql_cursor_fetch_

        self.__cmddict['sql_list_'] = self.sql_list_

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
        for cname in self.__conns.keys():
            self.__conns[cname].sql_close_(cname)
        return True

#----------------------------------------------------------------------
#
# Script API
#
#----------------------------------------------------------------------

    # open the db
    def sql_open_(self, cname, dbname, **kwargs):
        ''' Open a connection to a sqllite3 database file, creating the files
            if it doesn't exist.  The connection name and the database filename
            do not have to be the same.

            Options supported:
                    autocommit          : If True, write the changes to the file after
                                          every change. Default=True
                    check_same_thread   : If True, restrict callers to a single thread.
                                          Default=False
        '''

        dbpath = ''
        try:
            if not self.__lock.acquire(blocking=True, timeout=self.__locktimeout):
                return retError(self.__api, MODNAME, 'Could not open "'+cname+'"', False)

            # check the format of the connection name
            if not checkFileName(cname):
                return retError(self.__api, MODNAME, 'invalid name:'+cname)

            # check the format of the db name
            if not checkFileName(dbname):
                return retError(self.__api, MODNAME, 'invalid database name:'+dbname)

            # check for duplicate connection names
            if cname in self.__conns:
                unlock__(self.__lock)
                return retError(self.__api, MODNAME, 'name already used:'+cname, False)

            # add a root path prefix if configured
            if self.sqlroot:
                dbpath = self.sqlroot+'/'
            # and add the extension
            dbpath = dbpath+dbname+'.'+self.sqlext

            m = SqlLiteConnection(cname,  self.__api)
            if m != None:
                cflag = m.sql_open_(dbpath, **kwargs)
                if cflag == True:
                    self.__conns[cname] = m
                    unlock__(self.__lock)
                    return True
                else:
                    m = None
            unlock__(self.__lock)
            return False
        except Exception as e:
            unlock__(self.__lock)
            return retError(self.__api, MODNAME, 'Error in sql_open_ '+'"'+cname+'":'+str(e), False)
        return False

    # close the db
    def sql_close_(self, cname):
        ''' Close an open db connection '''

        try:
            if not self.__lock.acquire(blocking=True, timeout=self.__locktimeout):
                return retError(self.__api, MODNAME, 'Could not close "'+cname+'"', False)

            if cname not in self.__conns:
                unlock__(self.__lock)
                return retError(self.__api, MODNAME, 'name not found:'+cname, False)

            self.__conns[cname].sql_close_()
            del self.__conns[cname]
            unlock__(self.__lock)
        except Exception as e:
            unlock__(self.__lock)
            return retError(self.__api, MODNAME, 'Error in sql_close_ '+'"'+name+'":'+str(e), False)
        return True

    def sql_execute_(self, cname, sql, *args, **kwargs):
        ''' Execute a SQL statement in an open db '''

        if cname not in self.__conns.keys():
            return retError(self.__api, MODNAME, 'name not found:'+cname, None)

        return self.__conns[cname].sql_execute_(sql, *args, **kwargs)

    def sql_commit_(self, cname):
        ''' Commit pending updates '''

        if cname not in self.__conns.keys():
            return retError(self.__api, MODNAME, 'name not found:'+cname, False)

        return self.__conns[cname].sql_commit_()

    def sql_rollback_(self, cname):
        ''' Undo pending changes '''

        if cname not in self.__conns.keys():
            return retError(self.__api, MODNAME, 'name not found:'+cname, False)

        return self.__conns[cname].sql_rollback_()

    def sql_changes_(self, cname):
        ''' Return the number of recent updates '''

        if cname not in self.__conns.keys():
            return retError(self.__api, MODNAME, 'name not found:'+cname, -1)

        return self.__conns[cname].sql_changes_()

    def sql_cursor_fetch_(self, cname, cursor, count=0):
        ''' Return a cursor from the last execute_() '''

        if cname not in self.__conns.keys():
            return retError(self.__api, MODNAME, 'name not found:'+cname, None)

        return self.__conns[cname].sql_cursor_fetch_(cursor, count=0)


    def sql_list_(self):
        '''' Return a list[] of open connections '''

        ret = None
        try:
            if not self.__lock.acquire(blocking=True, timeout=self.__locktimeout):
                return retError(self.__api, MODNAME, 'Could not list sql conns', None)

            ret = list(self.__conns.keys())
            unlock__(self.__lock)
        except Exception as e:
            unlock__(self.__lock)
            return retError(self.__api, MODNAME, 'Error in sql_list_:'+str(e), None)

        return ret


#----------------------------------------------------------------------
#
# connection class
#
#----------------------------------------------------------------------

class SqlLiteConnection():
    '''
        This class represents a connection to a sqlite3 database.  There can be
        several connections active simultaneously, open to different database
        files.
    '''

    def __init__(self, name,  api):
        self.__name = name
        self.__api = api
        self.__dbname = ''

        self.__client = None
        self.__lock = threading.Lock()

    def sql_open_(self, dbname, **kwargs):
        """
            Open a database for use.

                Optional arguments:
                    autocommit=True -       Commits changes to the database after
                                                sql_execute_() call.  Default=False
                    check_same_thread=False Allow updates from multiple threads.
        """


        threadFlag = kwargs.get('check_same_thread', False)

        if self.__client:
            return False
        try:
            # try to open the sqlite3 database
            conn = sqlite3.connect(dbname,  check_same_thread=threadFlag)
            # wrap it in our local object
            self.__client = _SqlDatabase(dbname, conn, **kwargs)
            self.__dbname = dbname
            return True
        except Exception as e:
            return retError(self.__api, MODNAME, 'Error opening database '+'"'+dbname+'":'+str(e), False)
        return False


    def sql_close_(self):
        """
            Close the connection to database and clean-up
        """
        if self.__client == None:
            return False

        try:
            self.__client.conn_().close()
            self.__client.close_()
            if self.__lock.locked():
                self.__lock.release()
            return True
        except Exception as e:
            return retError(self.__api, MODNAME, 'Error closing database '+'"'+self.__dbname+'":'+str(e), False)
        return False


    def sql_execute_(self, sql, *args, **kwargs):
        """
            Submit a SQL statement to the database.

                Optional arguments:
                    args - values to replace ? in the sql statement
                    autocommit=True - Commits changes to the database after
                                        the execute_() call.  Default=False
        """
        if self.__client == None:
            return None

        # allow us to override the auto flag here
        autocommit = kwargs.pop('autocommit', False)

        try:
            rv = self.__lock.acquire(blocking=True, timeout=20)
            if rv == False:
                return retError(self.__api, MODNAME, 'Could not execute "'+sql+'"', None)
            # execute the statement with optional args
            ret = self.__client.conn_().execute(sql, args)
            # if autocommit is set, commit it
            if self.__client.auto_() or autocommit:
                self.__client.conn_().commit()
            self.__lock.release()
            return ret
        except Exception as e:
            if self.__lock.locked():
                self.__lock.release()
            return retError(self.__api, MODNAME, 'SQL error in "'+sql+'":'+str(e), None)
        return None


    def sql_commit_(self):
        """
            Commit any pending changes to the database
        """
        if self.__client == None:
            return False
        try:
            rv = self.__lock.acquire(blocking=True, timeout=20)
            if rv == False:
                return retError(self.__api, MODNAME, 'Could not commit to "'+self.__dbname+'"', None)
            self.__client.conn_().commit()
            self.__lock.release()
            return True
        except Exception as e:
            if self.__lock.locked():
                self.__lock.release()
            return retError(self.__api, MODNAME, 'Error committing database '+'"'+self.__dbname+'":'+str(e), False)
        return False


    def sql_rollback_(self):
        """
            Undo any changes since the last sql_commit_()
        """
        if self.__client == None:
            return False
        try:
            rv = self.__lock.acquire(blocking=True, timeout=20)
            if rv == False:
                return retError(self.__api, MODNAME, 'Could not roll back "'+self.__dbname+'"', None)
            self.__client.conn_().rollback()
            self.__lock.release()
            return True
        except Exception as e:
            if self.__lock.locked():
                self.__lock.release()
            return retError(self.__api, MODNAME, 'Error rolling back database '+'"'+self.__dbname+'":'+str(e), False)
        return False


    def sql_changes_(self):
        """
            Return the number of database changes since creation
        """
        if self.__client == None:
            return -1

        try:
            return (self.__client.conn_()).total_changes
        except Exception as e:
            return retError(self.__api, MODNAME, 'Error getting changes from '+'"'+self.__dbname+'":'+str(e), False)
        return -1

    # get rows from a cursor
    #   -1 = get the next row as a tuple
    #    0 = get all the rows as a list of tuples
    #   >0 = gets all rows <n> at a time as a list of tuples
    def sql_cursor_fetch_(self, cursor, count=0):
        """
            Get rows from a cursor (returned by sql_execute_())

            size parameter:
                -1 = get the next row as a tuple
                 0 = get all the rows as a list of tuples
                >0 = gets all rows <n> at a time as a list of tuples

        """
        if not cursor:
            return None

        ret = None

        try:
            rv = self.__lock.acquire(blocking=True, timeout=20)
            if rv == False:
                return retError(self.__api, MODNAME, 'Could not fetch cursor "'+self.__dbname+'"', None)

            if count < 0:
                ret = cursor.fetchone()
            elif count == 0:
                ret = cursor.fetchall()
            else:
                ret = cursor.fetchmany(size=count)
            self.__lock.release()
        except Exception as e:
            if self.__lock.locked():
                self.__lock.release()
            return retError(self.__api, MODNAME, 'Error fetching cursor from database '+'"'+self.__dbname+'":'+str(e), False)

        return ret



#----------------------------------------------------------------------
#
# Support functions
#
#----------------------------------------------------------------------

class _SqlDatabase:
    """
        This wraps the sqlite3 connection with some additional state info
    """

    def __init__(self, dbname, dbconn, **kwargs):
        self.__dbname = dbname
        self.__dbconn = dbconn
        # set the default autocommit
        self.__autocommit = kwargs.pop('autocommit', True)
        self.__threading = kwargs.get('check_same_thread', False)

    def close_(self):
        self.__dbconn = None

    def conn_(self):
        return self.__dbconn

    def auto_(self):
        return self.__autocommit

#----------------------------------------------------------------------
#
# Support functions
#
#----------------------------------------------------------------------

