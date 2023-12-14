#!/usr/bin/env python3
"""sqliteext - SQlite3 database functions.

This extension allows a script to store and retrieve data from a
sqlite3 database.  The database files are stored under a directory
passed in via the "sql_root" option.

Some basic knowledge of SqLite3 and SQL is helpful when using this
extension.

All functions are mutex-protected, and can be used from multiple threads.

Make the functions available to a script by adding:

    loadExtension_('sqliteext')

to it.  Functions exported by this extension:

Methods:

        sql_open_()         :   Open a sqlite3 database, creating it if it
                                doesn't exist.
        sql_close_()        :   Close an open connection.
        sql_execute_()      :   Execute a SQL command in the open database.
        sql_commit_()       :   Commit any pending transactions (in autocommit == False)
        sql_rollback_()     :   Roll back any pending transactions
        sql_changes_()      :   Return the number of rows recently altered
        sql_cursor_fetch_() :   Return rows from a cursor after an execute_()
        sql_list_()         :   Return a list[] of the active connection names

Note:
    Required Python modules:

        sqlite3

Credits:
    * version: 1.0
    * last update: 2023-Nov-20
    * License:  MIT
    * Author:  Mark Anacker <closecrowd@pm.me>
    * Copyright (c) 2023 by Mark Anacker

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
    """This class manages commands to use a sqlite3 database."""

    def __init__(self, api, options={}):
        """Constructs an instance of the SqLiteExt class.

        This instance will manage all connections to sqlite3 databases.
        There will be only one of these instances at a time.

            Args:

                api     : an instance of ExtensionAPI connecting us to the engine.

                options : a dict of option settings passed down to the extension.

            Returns:

                Nothing.

        Attributes:
            __api           : An instance of ExtensionAPI passed by the host, used
                                to call back into the engine.  Copied from api.

            __options       : A dict of options from the host that may or may not
                                apply to this extension.  Copied from options.


            __cmddict       : Dispatch table of our script command names and their
                                functions.

            __conns         : The table of active connections, indexed by name.

            __cmdsflag      : If True, install the "redis_cmd_()" function.  Set
                                in the options dict passed in.


            sqlroot         : The path to prepend to database file names.

            sqlext          : The file extension to append to database file names.

            __locktimeout   : Timeout in seconds to wait for a mutex.

            __lock          : Thread-locking mutex.

        Options:
                    'sql_root' : a path prepended to all database names,
                        restricting access to db files below this point.

                    'sql_ext' : filename extension to use for database files.
                        Defaults to '.db'

        """

        self.__api = api
        self.__options = options
        self.__cmddict = {}     # a dict holding our script functions

        if options:
            self.sqlroot = options.get('sql_root', None)
            self.sqlext = options.get('sql_ext', 'db')
        else:
            self.sqlroot = None
            self.sqlext = 'db'

        self.__conns = {}       # sqlite3 database connection names

        self.__dbnames = {}     # a list of filenames in use

        self.__locktimeout = 5
        self.__lock = threading.Lock()

    def register(self):
        """Make this extension's functions available to scripts.

        This method installs our script API methods as functions in the
        engine symbol table, making them available to scripts.

        This is called by the ExtensionMgr during loading.

        Note:
            Functions installed:
                * sql_open_()         :   Open a sqlite3 database, creating it if it doesn't exist.
                * sql_close_()        :   Close an open connection.
                * sql_execute_()      :   Execute a SQL command in the open database.
                * sql_commit_()       :   Commit any pending transactions (if autocommit is False)
                * sql_rollback_()     :   Roll back any pending transactions
                * sql_changes_()      :   Return the number of rows recently altered
                * sql_cursor_fetch_() :   Return rows from a cursor after an execute_()
                * sql_list_()         :   Return a list[] of the active connection names

        Args:

            None

        Returns

            True        :   Commands are installed and the extension is ready to use.

            False       :   Commands are NOT installed, and the extension is inactive.

        """

        if not modready:
            return False

        # Store our functions in the local dict
        self.__cmddict['sql_open_'] = self.sql_open_
        self.__cmddict['sql_close_'] = self.sql_close_
        self.__cmddict['sql_execute_'] = self.sql_execute_
        self.__cmddict['sql_commit_'] = self.sql_commit_
        self.__cmddict['sql_rollback_'] = self.sql_rollback_
        self.__cmddict['sql_changes_'] = self.sql_changes_
        self.__cmddict['sql_cursor_fetch_'] = self.sql_cursor_fetch_

        self.__cmddict['sql_list_'] = self.sql_list_

        # call the engine to add them
        self.__api.registerCmds(self.__cmddict)

        return True

    def unregister(self):
        """Remove this extension's functions from the engine. """

        if not modready:
            return False

        # call the engine to remove the script functions
        self.__api.unregisterCmds(self.__cmddict)

        return True

    def shutdown(self):
        """Perform a graceful shutdown.

        Close all of the active database connections.  This gets called
        by the extension manager just before the extension is unloaded.

        """
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
        """Handles the sql_open_() function.

        Open a connection to a sqllite3 database file, creating the files
        if it doesn't exist.  The connection name and the database filename
        do not have to be the same.

        A check is made to make sure the database filename  isn't already in use
        by another connection.  It's probably not a good idea to have the same
        file accessed by multiple connections simultaneously.  That's not the same
        as calling this extension from multiple threads (which is supported).

            Args:

                cname       :   The connection name to use. Must not be in use.

                dbname      :   The Sqlite3 database file to use.

                **kwargs    :   Options to pass down to sqlite3.

            Returns:

                True if the database was opened.

                False if an error occurred.

            Options:

                autocommit          : If True, write the changes to the file after every change. Default=True.

                check_same_thread   : If True, restrict callers to a single thread. Default=False.

        """

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

            # make sure we don't open the same file more than once
            if dbname in self.__dbnames:
                unlock__(self.__lock)
                return retError(self.__api, MODNAME, 'database already opened:'+dbname, False)

            # add a root path prefix if configured
            if self.sqlroot:
                dbpath = self.sqlroot+'/'
            # and add the extension
            dbpath = dbpath+dbname+'.'+self.sqlext

            # create a connection object
            m = SqlLiteConnection(cname, dbname, self.__api)
            if m != None:
                # and try to open it
                cflag = m.sql_open_(dbpath, **kwargs)
                if cflag == True:
                    # save the connection name
                    self.__conns[cname] = m
                    # and the database file name
                    self.__dbnames[dbname] = cname
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
        """Handles the sql_close_() function.

        Close an open db connection and remove the connection from the table.

            Args:

                cname   :   The name of the connection to remove.

            Returns:

                The return value. True for success, False otherwise.

        """

        try:
            if not self.__lock.acquire(blocking=True, timeout=self.__locktimeout):
                return retError(self.__api, MODNAME, 'Could not close "'+cname+'"', False)

            if cname not in self.__conns:
                unlock__(self.__lock)
                return retError(self.__api, MODNAME, 'name not found:'+cname, False)

            # get the dbname from the connection
            dbname = self.__conns[cname].sql_get_dbname_()
            # close the database
            self.__conns[cname].sql_close_()
            # remove it from the table
            del self.__conns[cname]
            # if the dbname is in the name table
            if dbname in self.__dbnames:
                # remove it
                del self.__dbnames[dbname]
            unlock__(self.__lock)
        except Exception as e:
            unlock__(self.__lock)
            return retError(self.__api, MODNAME, 'Error in sql_close_ '+'"'+name+'":'+str(e), False)
        return True

    def sql_execute_(self, cname, sql, *args, **kwargs):
        """Handles the sql_execute_() function.

        Execute a SQL statement in an open db.

            Args:

                cname       :   The connection name to use.

                sql         :   The SQL statement to execute.

                *args       :   Values to substitute in the above SQL (if any).

                **kwargs    :   Options to pass down to sqlite3.

            Returns:

                A cursor reference if successful.

                None if there was an error.

        """

        if cname not in self.__conns.keys():
            return retError(self.__api, MODNAME, 'name not found:'+cname, None)

        return self.__conns[cname].sql_execute_(sql, *args, **kwargs)

    def sql_commit_(self, cname):
        """Handles the sql_commit_() function.

        Commit pending updates to the database.  If autocommit is True,
        this function has no effect.

            Args:

                cname   :   The name of the connection to commit.

            Returns:

                True for success, False otherwise.

        """

        if cname not in self.__conns.keys():
            return retError(self.__api, MODNAME, 'name not found:'+cname, False)

        return self.__conns[cname].sql_commit_()

    def sql_rollback_(self, cname):
        """Handles the sql_rollback_() function.

        Rollback pending changes.

        If autocommit is False, updates to the database are held in a buffer
        until sql_commit_() is called.  This function clears that buffer,
        effectively reverting changes back to the last sql_commit_().  If
        autocommit is True, this function has no effect.

            Args:

                cname   :   The name of the connection to use.

            Returns:

                The return value. True for success, False otherwise.

        """

        if cname not in self.__conns.keys():
            return retError(self.__api, MODNAME, 'name not found:'+cname, False)

        return self.__conns[cname].sql_rollback_()

    def sql_changes_(self, cname):
        """Handles the sql_cursor_fetch_() function.

       Returns the number of changes to the database since it was last
       opened.

            Args:

                cname   :   The name of the connection to use.

            Returns:

                The number of updates in this session.

                -1 if there was an error.

      """

        if cname not in self.__conns.keys():
            return retError(self.__api, MODNAME, 'name not found:'+cname, -1)

        return self.__conns[cname].sql_changes_()

    def sql_cursor_fetch_(self, cname, cursor, count=0):
        """Handles the sql_cursor_fetch_() function.

        Return one or many rows from the supplied cursor (returned by sql_execute_()).

            Args:

                cname   :   The name of the connection to use.

                cursor  :   The cursor reference returned by sql_execute_().

                count   :   The number of rows to return.

                                * -1 = get the next row as a tuple.
                                * 0 = get all the rows as a list of tuples.
                                * >0 = gets all rows <n> at a time as a list of tuples.

            Returns:

                The requested number of rows, None if an error occurred.

        """

        if cname not in self.__conns.keys():
            return retError(self.__api, MODNAME, 'name not found:'+cname, None)

        return self.__conns[cname].sql_cursor_fetch_(cursor, count=0)


    def sql_list_(self):
        """Handles the sql_list_() function.

        Returns a list with the names of all current connections.

            Args:

                None

            Returns:

                A list[] of active connections.  The list may be empty if
                there are no connections.

                None if there was an error.
        """

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
    """
        This class represents a connection to a sqlite3 database.  There can be
        several connections active simultaneously, open to different database
        files.

    """

    def __init__(self, name, dbname, api):
        """Create a SqlLiteConnection object.

        Sets up the info for a single connection to a db file.

            Args:
                name    :   The name of this connection.

                dbname  :   The base name of the database file.

                api     :   A reference back to the engine API.  Used for error messages.

            Returns:
                None

        """

        self.__name = name
        self.__api = api
        self.__dbname = dbname
        self.__dbpath = ''

        self.__client = None
        self.__lock = threading.Lock()

    def sql_open_(self, dbpath, **kwargs):
        """Open a database for use.

        This method tries to connect to a Sqlite3 database file.

            Args:
                dbpath      :   The full pathname of the Sqlite3 db file.

                **kwargs    :   Options to pass down to sqlite3.

            Returns:
                True if the database was opened.

                False if there was an error.

            Options:
                    * autocommit=True   :   Commits changes to the database after sql_execute_() call.  Default=False

                    * check_same_thread=False   :   Allow updates from multiple threads.

        """

        threadFlag = kwargs.get('check_same_thread', False)

        if self.__client:
            return False
        try:
            # try to open the sqlite3 database
            conn = sqlite3.connect(dbpath, check_same_thread=threadFlag)
            # wrap it in our local object
            self.__client = _SqlDatabase(dbpath, conn, **kwargs)
            self.__dbpath = dbpath
            return True
        except Exception as e:
            return retError(self.__api, MODNAME, 'Error opening database '+'"'+dbpath+'":'+str(e), False)
        return False


    def sql_close_(self):
        """
            Close the connection to database and clean-up.
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
        """Execute a sql statement.

            Submit a SQL statement to the database.

                Args:
                    sql         :   The SQL statement to execute.

                    *args       :   Values to substitute in the above SQL (if any).

                    **kwargs    :   Options to pass down to sqlite3.

                Returns:
                    A cursor reference if successful.

                    None if there was an error.

                Options:
                    args - values to replace ? in the sql statement.

                    autocommit=True - Commits changes to the database after
                                        the execute_() call.  Default=False.

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
        """Handles the sql_commit_() function.

        Commit pending updates to the database.  If autocommit is True,
        this function has no effect.

            Args:
                None
            Returns:
                The return value. True for success, False otherwise.

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
        """Rollback pending changes.

        If autocommit is False, updates to the database are held in a buffer
        until sql_commit_() is called.  This function clears that buffer,
        effectively reverting changes back to the last sql_commit_().  If
        autocommit is True, this function has no effect.

            Args:
                None
            Returns:
                The return value. True for success, False otherwise.

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
        """Return the number of recent updates.

       Returns the number of changes to the database since it was last
       opened.

            Args:
                None
            Returns:
                The number of updates in this session.
                -1 if there was an error.

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
        """Get rows from a cursor (returned by sql_execute_()).

        Return one or many rows from the supplied cursor.

            Args:
                cursor  :   The cursor reference returned by sql_execute_().
                count   :   The number of rows to return.
                                * -1 = get the next row as a tuple.
                                * 0 = get all the rows as a list of tuples.
                                * >0 = gets all rows <n> at a time as a list of tuples.
            Returns:
                The requested number of rows.
                None if an error occurred.

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

    def sql_get_dbname_(self):
        """Return this connection's db file name ."""

        return self.__dbname


#----------------------------------------------------------------------
#
# Support functions
#
#----------------------------------------------------------------------

class _SqlDatabase:
    """Sqllite3 database proxy objext.

        This wraps the sqlite3 connection with some additional state info

    """

    def __init__(self, dbpath, dbconn, **kwargs):
        self.__dbpath = dbpath  # full path to the db file
        self.__dbconn = dbconn  # the connection that created us
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

