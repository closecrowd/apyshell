#!/usr/bin/env python3
"""redisext - basic interface to the Redis cache.

This extension provides a client connection to a redis in-memory
cache.  Not all redis functions are avaiable (there are a *lot* of
them), but a lot of the useful ones are included.

Familiarity with redis is helpful. See: https://redis.io/commands/

Make the functions available to a script by adding:

    loadExtension_('redisext')

to it.  Functions exported by this extension:

Methods:

        redis_connect_()    : Connect to a redis server
        redis_disconnect_() : Disconnect from the server
        redis_list_()       : Return a list[] of active connections
        redis_cmd_()        : Pass a command string to redis *

            these map directly to redis_cli commands:
        redis_set_()        : Set a value in the cache
        redis_get_()        : Get a value from the cache
        redis_del_()        : Remove a keyed entry from the cache
        redis_incr_()       : Increments the number stored at key by one
        redis_decr_()       : Decrements the number stored at key by one
        redis_hset_()       : Sets the value associated in a hash stored at key.
        redis_hmset_()      : Sets multiple values in a hash
        redis_hget_()       : Returns the value associated in a hash stored at key.
        redis_hdel_()       : Removes the specified fields from the hash stored at key
        redis_hkeys_()      : Returns all field names in the hash stored at key.
        redis_hvals_()      : Returns all values in the hash stored at key.

    * may be disabled by option settings

Options:

    allow_redis_cmds    If True, installs the "redis_cmd_" function
                        to pass complete redis command strings to the
                        server.  This is a potential security risk.

Note:
    Required Python modules:

        redis

Credits:
    * version: 1.0
    * last update: 2023-Nov-20
    * License:  MIT
    * Author:  Mark Anacker <closecrowd@pm.me>
    * Copyright (c) 2023 by Mark Anacker

"""

import threading

modready = True
try:
    import redis
except Exception as ex:
    modready = False
    print('import failed:', ex)

from support import *
from extensionapi import *

##############################################################################

#
# Globals
#

__key__ = 'redisext'
__cname__ = 'RedisExt'

MODNAME = "redisext"

defaultName = 'redisconn'

##############################################################################

# ----------------------------------------------------------------------------
#
# Extension class
#
# ----------------------------------------------------------------------------

class RedisExt():
    """This class manages connections to a Redis cache server."""

    def __init__(self, api, options={}):
        """Constructs an instance of the RedisExt class.

        This instance will manage all connections to one or mode redis
        servers.  There will be only once of these instances at a time.

            Args:

                api     : an instance of ExtensionAPI connecting us to the engine.

                options : a dict of option settings passed down to the extension.

            Returns:

                None

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

                __locktimeout   : Timeout in seconds to wait for a mutex.

                __lock          : Thread-locking mutex.

        """

        self.__api = api
        self.__options = options
        self.__cmddict = {}

        self.__conns = {}   # redis connection objects
        self.__cmdsflag = options.get('allow_redis_cmds', False)

        self.__locktimeout = 5
        self.__lock = threading.Lock()

    def register(self):
        """Make this extension's functions available to scripts.

        This method installs our script API methods as functions in the
        engine symbol table, making them available to scripts.

        This is called by the ExtensionMgr during loading.

        Note:
            Functions installed:
                * redis_connect_()    : Connect to a redis server
                * redis_disconnect_() : Disconnect from the server
                * redis_list_()       : Return a list[] of active connections
                * redis_cmd_()        : Pass a command string to redis [OPT]

                    these map directly to redis_cli commands:
                * redis_set_()        : Set a value in the cache
                * redis_get_()        : Get a value from the cache
                * redis_del_()        : Remove a keyed entry from the cache
                * redis_incr_()       : Increments the number stored at key by one
                * redis_decr_()       : Decrements the number stored at key by one
                * redis_hset_()       : Sets the value associated in a hash stored at key.
                * redis_hmset_()      : Sets multiple values in a hash
                * redis_hget_()       : Returns the value associated in a hash stored at key.
                * redis_hdel_()       : Removes the specified fields from the hash stored at key
                * redis_hkeys_()      : Returns all field names in the hash stored at key.
                * redis_hvals_()      : Returns all values in the hash stored at key.

                [OPT] may be disabled by option settings

            Args:

                None

            Returns:

                True        :   Commands are installed and the extension is ready to use.

                False       :   Commands are NOT installed, and the extension is inactive.

        """

        if not modready:
            return False

        try:
            self.__cmddict['redis_connect_'] = self.connect_
            self.__cmddict['redis_disconnect_'] = self.disconnect_

            self.__cmddict['redis_list_'] = self.list_

            if self.__cmdsflag:
                self.__cmddict['redis_cmd_'] = self.cmd_

            self.__cmddict['redis_set_'] = self.set_
            self.__cmddict['redis_get_'] = self.get_
            self.__cmddict['redis_del_'] = self.del_
            self.__cmddict['redis_incr_'] = self.incr_
            self.__cmddict['redis_decr_'] = self.decr_

            self.__cmddict['redis_hset_'] = self.hset_
            self.__cmddict['redis_hmset_'] = self.hmset_
            self.__cmddict['redis_hget_'] = self.hget_
            self.__cmddict['redis_hdel_'] = self.hdel_
            self.__cmddict['redis_hkeys_'] = self.hkeys_
            self.__cmddict['redis_hvals_'] = self.hvals_

            self.__api.registerCmds(self.__cmddict)
        except Exception as e:
            print(str(e))

        return True

    def unregister(self):
        """Remove this extension's functions from the engine. """

        if not modready:
            return False

        # unregister the extensions script functions
        self.__api.unregisterCmds(self.__cmddict)

        return True

    def shutdown(self):
        """Perform a graceful shutdown.

        Close all of the active Redis connections.  This gets called
        by the extension manager just before the extension is unloaded.

        """

        for cname in self.__conns.keys():
            self.__conns[cname].disconnect_(cname)
        return True

#----------------------------------------------------------------------
#
# Script API
#
#----------------------------------------------------------------------

    def connect_(self, cname=defaultName, host='127.0.0.1', port=6379, **kwargs):
        """Handles the redis_connect_() function.

        This function establishes a named connection to a redis server.
        Successful completion is required before any other functions
        may be used (except redis_list_).

            Args:

                cname:      The name of the connection

                host:       The hostname or ip address of the server

                port:       The port to connect to the server on

                **kwargs:   Optional arguments

            Returns:

                The return value. True for success, False otherwise.

        """

        try:
            if not self.__lock.acquire(blocking=True, timeout=self.__locktimeout):
                return retError(self.__api, MODNAME, 'Could not open "'+cname+'"', False)

            if cname in self.__conns.keys():
                unlock__(self.__lock)
                return retError(self.__api, MODNAME, 'name already used:'+cname, False)

            m = RedisConnection(cname, self.__api)
            if m != None:
                cflag = m.connect_(host, port)
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
            return retError(self.__api, MODNAME, 'Error in connect_ '+'"'+cname+'":'+str(e), False)
        return False

    def disconnect_(self, cname=defaultName):
        """Handles the redis_disconnect_() function.

        Closes an open connection to a redis server and
        removes the connection from the table.

            Args:

                cname:      The name of the connection to remove

            Returns:

                The return value. True for success, False otherwise.

        """

        try:
            if not self.__lock.acquire(blocking=True, timeout=self.__locktimeout):
                return retError(self.__api, MODNAME, 'Could not close "'+cname+'"', False)

            if cname not in self.__conns.keys():
                return retError(self.__api, MODNAME, 'name not found:'+cname, False)

            self.__conns[cname].disconnect_()
            del self.__conns[cname]
            unlock__(self.__lock)
            return True
        except Exception as e:
            unlock__(self.__lock)
            return retError(self.__api, MODNAME, 'Error in disconnect_ '+'"'+cname+'":'+str(e), False)
        return False


    def list_(self):
        """Handles the redis_list_() function.

        This method returns a list[] of active Redis connections.

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
                return retError(self.__api, MODNAME, 'Could not list redis conns', None)

            ret =  list(self.__conns.keys())
            unlock__(self.__lock)
        except Exception as e:
            unlock__(self.__lock)
            return retError(self.__api, MODNAME, 'Error in listConns_:'+str(e), None)

        return ret

#
# data functions
#

# optional command processor

    def cmd_(self, cname, *args):
        """Handles the redis_cmd_() function.

        Sends a raw command directly to the redis server. This is potentially
        dangerous, and is only available if specifically enabled by the host
        application via the options.

            Args:

                cname:      The name of the connection to use.

                *args:      The arguments to pass to the execute_command function.

            Returns:

                The results of the command.

                None if there was an error

        """

        if cname not in self.__conns.keys():
            return retError(self.__api, MODNAME, 'name not found:'+cname, None)
        return self.__conns[cname].cmds_(*args)

#
# key:value functions
#

    def set_(self, cname, key, value):
        """Handles the redis_set_() function. """

        if cname not in self.__conns.keys():
            return retError(self.__api, MODNAME, 'name not found:'+cname)
        return self.__conns[cname].cmds_('SET', key, value)

    def get_(self, cname, key):
        """Handles the redis_get_() function. """

        if cname not in self.__conns.keys():
            return retError(self.__api, MODNAME, 'name not found:'+cname)
        return self.__conns[cname].cmds_('GET', key)

    def del_(self, cname, key):
        """Handles the redis_del_() function. """

        if cname not in self.__conns.keys():
            return retError(self.__api, MODNAME, 'name not found:'+cname)
        return self.__conns[cname].cmds_('DEL', key)

    def incr_(self, cname, key, val=1):
        """Handles the redis_incr_() function. """

        if cname not in self.__conns.keys():
            return retError(self.__api, MODNAME, 'name not found:'+cname)
        return self.__conns[cname].cmds_('INCRBY', key, val)

    def decr_(self, cname, key, val=1):
        """Handles the redis_decr_() function. """

        if cname not in self.__conns.keys():
            return retError(self.__api, MODNAME, 'name not found:'+cname)
        return self.__conns[cname].cmds_('DECRRBY', key, val)

# hash functions

    def hset_(self, cname, hashname, key, value=''):
        """Handles the redis_hset_() function. """

        if cname not in self.__conns.keys():
            return retError(self.__api, MODNAME, 'name not found:'+cname)
        return self.__conns[cname].cmds_('HSET', hashname, key, value)

    # calls a helper function directly
    def hmset_(self, cname, hashname, map):
        """Handles the redis_hmset_() function. """

        if cname not in self.__conns.keys():
            return retError(self.__api, MODNAME, 'name not found:'+cname)
        return self.__conns[cname].hmset_(hashname, map)

    def hget_(self, cname, hashname, key):
        """Handles the redis_hget_() function. """

        if cname not in self.__conns.keys():
            return retError(self.__api, MODNAME, 'name not found:'+cname)
        return self.__conns[cname].cmds_('HGET', hashname, key)

    def hdel_(self, cname, hashname, key):
        """Handles the redis_hdel_() function. """

        if cname not in self.__conns.keys():
            return retError(self.__api, MODNAME, 'name not found:'+cname)
        return self.__conns[cname].cmds_('HDEL', hashname, key)

    def hkeys_(self, cname, hashname):
        """Handles the redis_hkeys_() function. """

        if cname not in self.__conns.keys():
            return retError(self.__api, MODNAME, 'name not found:'+cname)
        return self.__conns[cname].cmds_('HKEYS', hashname)

    def hvals_(self, cname, hashname):
        """Handles the redis_hvals_() function. """

        if cname not in self.__conns.keys():
            return retError(self.__api, MODNAME, 'name not found:'+cname)
        return self.__conns[cname].cmds_('HVALS', hashname)



#----------------------------------------------------------------------
#
# connection class
#
#----------------------------------------------------------------------

class RedisConnection():
    """
        This class represents a connection to a Redis server.  There can be
        several connections active simultaneously, open to different servers
        (or possibly the same server).
    """

    def __init__(self, name, api):
        self.__api = api                # the engine callback API
        self.__name = name              # the name of this connection
        self.__host = '127.0.0.1'       # default redis server
        self.__port = 6379              # and port
        self.__db = 0

        self.__client = None

    def connect_(self, host='127.0.0.1', port=6379, db=0):
        """Connect to the Redis server."""

        if self.__client != None:
            return False

        if not host:
            return False

        self.__host = host
        self.__port = port
        self.__db = db

# things we might use in the future
#        args = {}
#        args['db'] = kwargs.get('db', 0)
#        args['decode_responses'] = kwargs.get('decode_responses', True)
#        args['retry_on_timeout'] = kwargs.get('retry_on_timeout', True)
#        args['health_check_interval'] = kwargs.get('health_check_interval', 0)
#        args['username'] = kwargs.get('username', None)
#        args['password'] = kwargs.get('password', None)
#        args[''] = kwargs.get('', True)

        try:
            self.__client = redis.Redis( host=host, port=port, db=db, decode_responses=True)
        except Exception as ex:
            print(str(ex))
            self.__client = None

        return True

    def disconnect_(self):
        """Disconnect from the Redis server."""

        if self.__client != None:
            self.__client = None

    # redis command processor
    def cmds_(self, *args):
        """Send a command directly to the server."""

        if self.__client == None:
            return None

        return self.__client.execute_command(*args)

    # load a dict directly into a hashmap
    def hmset_(self, *args):
        """Load a whole dict into a redis hashmap."""

        if self.__client == None:
            return None

        return self.__client.hmset(*args)


#----------------------------------------------------------------------
#
# Support functions
#
#----------------------------------------------------------------------

