#!/usr/bin/env python3
"""mqttext -mqtt client commands

This extension implements a client for the MQTT pub/sub protocol.
It can handle multiple connections to MQTT brokers, publish messages
to topics, and subscribe to topics.  Incoming messages on subscribed
topics may be delivered by polling, or by callbacks.

The link to a broker is represented by a connection name.  Each
connection is separate from the others, and each may have multiple
topics subscribed to it.

Make the functions available to a script by adding:

    loadExtension_('mqttext')

to it.  Functions exported by this extension:

Methods:
        mqtt_connect_()     : Create a named connection to a broker
        mqtt_disconnect_()  : Close a named connection
        mqtt_list_()        : List all currently-active connections
        mqtt_subscribe_()   : Subscribe a connection to a topic
        mqtt_unsubscribe_() : Remove a subscription from a connection
        mqtt_isrunning_()   : True is the connection is attached to a broker
        mqtt_waiting_()     : The number of messages waiting to be read
        mqtt_readmsg_()     : Return the first availabel message on the connection
        mqtt_sendmsg_()     : Send a message to a given topic

Note:
    Required Python modules:

        paho.mqtt.client

Credits:
    * version: 1.0.0
    * last update: 2024-Jan-05
    * License:  MIT
    * Author:  Mark Anacker <closecrowd@pm.me>
    * Copyright (c) 2023,2024 by Mark Anacker

"""

import os
from queue import Queue
from types import *

from support import *
from extensionapi import *

modready = True
try:
    import paho.mqtt.client as mqtt
except Exception as ex:
    modready = False
    print('import failed:', ex)

##############################################################################

#
# Globals
#

__key__ = 'mqttext'
__cname__ = 'MqttExt'
MODNAME = "mqttext"

# defaultName = 'mqttconn'

##############################################################################

DEBUG = False
DEBUG=True
def debug(*args):
    if DEBUG:
        print(MODNAME, str(args))

# ----------------------------------------------------------------------------
#
# Extension class
#
# ----------------------------------------------------------------------------

class MqttExt():
    """This class manages commands to send/receive mqtt messages """

    def __init__(self, api, options={}):
        """Constructs an instance of the MqttExt class.

        This instance will manage all connections to mqtt brokers.
        There will be only once of these instances at a time.

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

            __locktimeout   : Timeout in seconds to wait for a mutex.

            __lock          : Thread-locking mutex.

        """

        self.__api = api
        self.__options = options

        self.__cmddict = {}

        self.__conns = {}   # mqtt connection objects

        if 'CallbackAPIVersion' in mqtt.__dict__:
            self.__pahover = 2
        else:
            self.__pahover = 1


    def register(self):
        """Make this extension's functions available to scripts.

        This method installs our script API methods as functions in the
        engine symbol table, making them available to scripts.

        This is called by the ExtensionMgr during loading.

        Note:
            Functions installed:
                * mqtt_connect_()     : Create a named connection to a broker
                * mqtt_disconnect_()  : Close a named connection
                * mqtt_list_()        : List all currently-active connections
                * mqtt_subscribe_()   : Subscribe a connection to a topic
                * mqtt_unsubscribe_() : Remove a subscription from a connection
                * mqtt_isrunning_()   : True is the connection is attached to a broker
                * mqtt_waiting_()     : The number of messages waiting to be read
                * mqtt_readmsg_()     : Return the first availabel message on the connection
                * mqtt_sendmsg_()     : Send a message to a given topic

            Args:
                None

            Returns:

                True        :   Commands are installed and the extension is ready to use.

                False       :   Commands are NOT installed, and the extension is inactive.

        """

        if not modready:
            return False

        try:
            self.__cmddict['mqtt_connect_'] = self.connect_
            self.__cmddict['mqtt_disconnect_'] = self.disconnect_
            self.__cmddict['mqtt_isrunning_'] = self.isrunning_

            self.__cmddict['mqtt_subscribe_'] = self.subtopic_
            self.__cmddict['mqtt_unsubscribe_'] = self.unsubtopic_
            self.__cmddict['mqtt_waiting_'] = self.waiting_
            self.__cmddict['mqtt_readmsg_'] = self.readmsg_
            self.__cmddict['mqtt_sendmsg_'] = self.sendmsg_

            self.__cmddict['mqtt_list_'] = self.listConns_

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

        Close all of the active MQTT connections.  This gets called
        by the extension manager just before the extension is unloaded.

        """

        for cname in self.__conns.keys():
            self.__conns[cname].disconnect_(cname)
        return True

# ----------------------------------------------------------------------
#
# Script API
#
# ----------------------------------------------------------------------

    # connect to a broker
    def connect_(self, cname, **kwargs):
        """Handles the mqtt_connect_() function.

        Create a connection object and establish a connection to a broker.

            Args:

                cname       : The name of the connection

                **kwargs    : A dict with all of the required parameters

            Returns:

                The return value. True for success, False otherwise.

        """

        debugMsg(MODNAME, 'mqtt:connect:', kwargs, type(kwargs))

        # check the format of the connection name
        if not checkFileName(cname):
            return retError(self.__api, MODNAME, 'invalid name:'+cname, False)

        # check for duplicate connection names
        if cname in self.__conns.keys():
            return retError(self.__api, MODNAME, 'name already used:'+cname, False)

        m = MqttConnection(cname, self.__api)
        if m is not None:
            self.__conns[cname] = m
        return m.connect_(**kwargs)

    # drop a broker
    def disconnect_(self, cname):
        """Handles the mqtt_disconnect_() function.

        Closes an open connection to a broker, and removes the connection
        from the table.

            Args:

                cname:      The name of the connection to remove

            Returns:

                The return value. True for success, False otherwise.

        """

        # check the format of the connection name
        if not checkFileName(cname):
            return retError(self.__api, MODNAME, 'invalid name:'+cname, False)

        # check for unknown connection name
        if cname not in self.__conns.keys():
            return retError(self.__api, MODNAME, 'name not found:'+cname, False)

        self.__conns[cname].disconnect_()
        del self.__conns[cname]
        return True

    # connection active?
    def isrunning_(self, cname):

        # check the format of the connection name
        if not checkFileName(cname):
            return retError(self.__api, MODNAME, 'invalid name:'+cname, False)

        # check for unknown connection name
        if cname not in self.__conns.keys():
            return retError(self.__api, MODNAME, 'name not found:'+cname, False)

        return self.__conns[cname].isrunning_()


    # subscribe to a topic
    def subtopic_(self, cname, topic, handler=None, qos=0):

        debugMsg(MODNAME, 'mqtt:sub:',  cname,  topic)

        # check the format of the connection name
        if not checkFileName(cname):
            return retError(self.__api, MODNAME, 'invalid name:'+cname, False)

        # check for unknown connection name
        if cname not in self.__conns.keys():
            return retError(self.__api, MODNAME, 'name not found:'+cname, False)

        return self.__conns[cname].subtopic_(topic, handler, qos)

    # cancel the subscription
    def unsubtopic_(self, cname, topic):

        # check the format of the connection name
        if not checkFileName(cname):
            return retError(self.__api, MODNAME, 'invalid name:'+cname, False)

        # check for unknown connection name
        if cname not in self.__conns.keys():
            return retError(self.__api, MODNAME, 'name not found:'+cname, False)

        return self.__conns[cname].unsubtopic_(topic)


    # number of messages waiting
    def waiting_(self, cname):

        # check the format of the connection name
        if not checkFileName(cname):
            return retError(self.__api, MODNAME, 'invalid name:'+cname, False)

        # check for unknown connection name
        if cname not in self.__conns.keys():
            return retError(self.__api, MODNAME, 'name not found:'+cname, False)

        return self.__conns[cname].waiting_()

    # read the next avail msg from the queue
    def readmsg_(self, cname, blocking=True, timeout=1):
        debugMsg(MODNAME, "mqtt read:", cname)

        # check the format of the connection name
        if not checkFileName(cname):
            return retError(self.__api, MODNAME, 'invalid name:'+cname, False)

        # check for unknown connection name
        if cname not in self.__conns.keys():
            return retError(self.__api, MODNAME, 'name not found:'+cname, False)

        return self.__conns[cname].readmsg_(blocking, timeout)

    # post a messsage to a topic
    def sendmsg_(self, cname, dest, data, qos=0, retain=False):

        # check the format of the connection name
        if not checkFileName(cname):
            return retError(self.__api, MODNAME, 'invalid name:'+cname, False)

        # check for unknown connection name
        if cname not in self.__conns.keys():
            return retError(self.__api, MODNAME, 'name not found:'+cname, False)

        return self.__conns[cname].sendmsg_(dest, data, qos, retain)

    # list the active connections
    def listConns_(self):
        '''
        Return a list[] of open connections.

            Args:

                None

            Returns:

                A list[] of active connections.  The list may be empty if
                there are no connections.

                None if there was an error.
        '''
        return list(self.__conns.keys())


# ----------------------------------------------------------------------
#
# connection class
#
# ----------------------------------------------------------------------

class MqttConnection():
    """
        This class represents a connection to a broker.  There can be
        several connections active simultaneously, linked to different
        brokers.  Or all to the same broker, but that would be inefficient.

    """
    def __init__(self, name, api):
        self.__api = api                # ExtensionManager API

        self.__connname = name          # connection name
        # user parameters - defaults
        self.__name = ''
        self.__handler = None

        self.__broker = '127.0.0.1'
        self.__bport = 1883

        self.__username = None          # broker authentication
        self.__password = None

        self.__tlscafile = None         # link security
        self.__tlscertfile = None
        self.__tlskeyfile = None
        self.__tlsvers = None
        self.__tlsinsecure = False

        self.__kainterval = 30          # keep-alive interval
        self.__clientid = 'mqtt'
        self.__timeout = 10
        self.__autoreconnect = True     # reconnect if the link goes away
        self.__tos = 0                  # see MQTT TOS specs


        # run-time vars
        self.__connected = False
        self.__running = False
        self.__maxqueue = 100
        self.__inqueue = Queue(self.__maxqueue)     # msg recv queue
        self.__subqueue = Queue(20)   # topic sub queue

        self.__topics = set()       # current topics
        self.__topichandlers = {}   # per-topic script handlers
        self.__wildcardhandlers = {}
        self.__client = None

        if 'CallbackAPIVersion' in mqtt.__dict__:
            self.__pahover = 2
        else:
            self.__pahover = 1


    def connect_(self, **kwargs):

        if self.__client:
            self.disconnect_()

        # set all of the user-configurable parameters
        self.__name = kwargs.get('name', '')
        self.__broker = kwargs.get('broker', '127.0.0.1')
        self.__bport = int( kwargs.get('port', 1883) )

        self.__clientid = kwargs.get('clientid', 'mqtt'+str(os.getpid()))
        self.__timeout = int( kwargs.get('timeout', 10) )
        self.__tos = int( kwargs.get('tos', 0) )
        self.__autoreconnect = kwargs.get('reconnect', True)
        self.__kainterval = int( kwargs.get('keepalive', 30) )

        self.__username = kwargs.get('username', None)
        self.__password = kwargs.get('password', None)

        self.__tlscafile = kwargs.get('tlscafile', None)
        self.__tlscertfile = kwargs.get('tlscertfile', None)
        self.__tlskeyfile = kwargs.get('tlskeyfile', None)
        self.__tlsvers = kwargs.get('tlsvers', None)
        self.__tlsinsecure = kwargs.get('tlsinsecure', False)

        self.__handler = kwargs.get('handler', None)

        try:
            self.connectclient()
        except Exception as e:
            self.__client = None
            debug("connection failed:", str(e))
            return False

        self.__client.loop_start()
        self.__running = True
        debugMsg(MODNAME, "mqtt:", self.__name, "started")
        return True

    def disconnect_(self):
        debugMsg(MODNAME, "mqtt disconnect")
        self.__autoreconnect = False
        if self.__client is not None:
            self.__client.loop_stop()
            self.__running = False
            self.__client.disconnect()
            self.__client = None
        self.__connected = False


    def subtopic_(self, topic, handler=None, qos=0):
        if self.__client is None:
            return False

        if qos not in [0, 1, 2]:
            return False

        if not topic:
            return False

        if topic not in self.__topics:
            if not self.__connected:
                # defer the sub until later
                self.__subqueue.put((topic, handler, qos), False, 1)
                debugMsg(MODNAME, "mqtt: subscription queued:", topic)
                return True

            debugMsg(MODNAME, "mqtt: subscribing to:", topic)
            self.__topics.add(topic)
            self.__client.subscribe(topic, qos)
            # add a per-topic callback handler
            if handler is not None:
                tsplit = topic.split('/')
                if '+' in tsplit or '#' in tsplit:
                    self.__wildcardhandlers[topic] = handler
                    self.__client.message_callback_add(topic, self.on_wildcard_message)
                else:
                    self.__topichandlers[topic] = handler
                    self.__client.message_callback_add(topic, self.on_topic_message)
            return True
        return False

    def unsubtopic_(self, topic):
        if self.__client is None:
            return False
        if not self.__connected:
            return False

        if not topic:
            return False

        if topic in self.__topics:
            debugMsg(MODNAME, "mqtt: unsubscribing from:", topic)
            self.__topics.remove(topic)
            self.__client.unsubscribe(topic)
            if topic in self.__topichandlers:
                del self.__topichandlers[topic]
                self.__client.message_callback_remove(topic)

            if topic in self.__wildcardhandlers:
                del self.__wildcardhandlers[topic]
                self.__client.message_callback_remove(topic)

            return True
        return False

    def isrunning_(self):
        return self.__connected

    # number of messages waiting
    def waiting_(self):
        return self.__inqueue.qsize()

    # read the next avail msg from the queue
    def readmsg_(self, blocking=True, timeout=1):
        debugMsg(MODNAME, "mqtt readmsg_")
        if not self.__connected:
            return None
        try:
            msg = self.__inqueue.get(blocking, timeout)   # blocking, 1-second timeout
            return msg
        except:
            return None

    # send a message to a topic (or topics)
    def sendmsg_(self, dest, data, qos=0, retain=False):

        if self.__client is None:
            return False
        if not self.__connected:
            return False

        if not dest:
            return False
        if not data:
            return False

        if qos not in [0, 1, 2]:
            return False

        rv = True
        tl = list()

        # dest topics may be a list
        if isinstance(dest, list):
            tl = dest
        else:
            # or a string representation of a list
            if dest[0] == '[':
                tl = dest[1:-1].split(',')
            else:
                # or just a single string - make it a list
                tl.append(dest)

        if len(tl) < 1:
            return False

        # walk the list and send to all the topics
        for topic in tl:
            self.__client.publish(topic, payload=data, qos=qos, retain=retain)
#            rv = ret.is_published
        return rv


# ----------------------------------------------------------------------
#
# Support functions
#
# ----------------------------------------------------------------------


    def connectclient(self):
        debugMsg(MODNAME, "mqtt connect", self.__broker, self.__bport, self.__clientid, self.__name)

        if self.__client is None:
            self.__connected = False

            if self.__pahover == 2:
                # mqtt V2 api
                self.__client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, self.__clientid, clean_session=True, userdata=self.__name)
            else:
                # mqtt V1 api
                self.__client = mqtt.Client(self.__clientid, clean_session=True, userdata=self.__name)

            self.__client.on_connect = self.on_connect
            self.__client.on_disconnect = self.on_disconnect
            self.__client.on_message = self.on_message
            self.__client.max_queued_messages_set(0)
            self.__client.max_inflight_messages_set(40)

            # set user/password if given
            if self.__username is not None:
                self.__client.username_pw_set(self.__username, self.__password)

            # set up TLS
            if self.__tlscertfile is not None:
                if self.__tlsvers is None:
                    self.__client.tls_set(self.__tlscertfile)
                else:
                    self.__client.tls_set(self.__tlscertfile, self.__tlsvers)

            try:
                self.__client.connect_async(self.__broker, port=self.__bport, keepalive=self.__kainterval)
                debugMsg(MODNAME, "connect started")
            except:
                debug("mqtt connection failed")
                self.__client = None
        else:
            debugMsg(MODNAME, 'already connected:', self.__name)

    # quickly resub to all current topics
    def resuball(self):
        if self.__client is not None:
            return False

        for topic in self.__topics:
            self.subtopic(topic)

#
# Callbacks
#

    # we come here when a connection has succeeded.
    # any subs queued during the before-time are
    # added here
    def on_connect(self, client, userdata, flags, rc):
        debugMsg(MODNAME, "on_connect:", rc, userdata, client)
        if rc == 0:
            self.__connected = True
            # if we have deferred subscriptions queued up
            while self.__subqueue.qsize() > 0:
                topic, handler, qos = self.__subqueue.get(False)
                self.subtopic_(topic, handler, qos)
                debugMsg(MODNAME, "mqtt: subscribed to:", topic, handler, qos)
        else:
            self.__connected = False

    def on_disconnect(self, client, userdata, rc):
        debugMsg(MODNAME, "on_disconnect:", rc)
        self.__connected = False

    # general message callback
    def on_message(self, client, userdata, message):
        # tuple is mqtt params plus conn name
        intup = (str(message.payload.decode("utf-8")), message.topic, message.qos, message.retain, self.__name )
        try:
            # if they gave us a handler
            if self.__handler is not None:
                self.__api.handleEvents(self.__handler, intup )
            else:
                # otherwise, we're polled
                self.__inqueue.put(intup, False, 1)   # non-blocking
        except:
            errorMsg(MODNAME, 'on_message:exc')
            pass    # skipped on a full queue

    # handle messages with a per-topic handler
    def on_topic_message(self, client, userdata, message):

        # tuple is mqtt params plus conn name
        intup = (str(message.payload.decode("utf-8")), message.topic, message.qos, message.retain, self.__name )
        try:
            # if there's a handler for this topic
            # *** need wildcard match here
            if message.topic in self.__topichandlers:
                handler = self.__topichandlers[message.topic]
                self.__api.handleEvents(handler, intup )
            else:
                # otherwise, we're polled
                self.__inqueue.put(intup, False, 1)   # non-blocking
        except Exception as ex:
            errorMsg(MODNAME, 'on_topic_message:exc', str(ex))
            pass    # skipped on a full queue

    # handle messages with a per-topic handler - wildcard topics
    def on_wildcard_message(self, client, userdata, message):
        # tuple is mqtt params plus conn name
        intup = (str(message.payload.decode("utf-8")), message.topic, message.qos, message.retain, self.__name )
        try:
            # check each wildcard subscription for a match
            for wcsub in self.__wildcardhandlers:
                # if found, call the handler
                if topicmatch(wcsub, message.topic):
                    handler = self.__wildcardhandlers[wcsub]
                    self.__api.handleEvents(handler, intup )
                    return

            # otherwise, we're polled
            self.__inqueue.put(intup, False, 1)   # non-blocking
        except Exception as ex:
            errorMsg(MODNAME, 'on_wildcard_message:exc', str(ex))
            pass    # skipped on a full queue

# ----------------------------------------------------------------------
#
# Support functions
#
# ----------------------------------------------------------------------

def topicmatch(subsc, topic):
    subl, topic = subsc.split('/'), topic.split('/')
    for i in range(len(subl)):
        e = subl[i]
        if e == '#':
            return True
        if e == '+':
            continue
        if e != topic[i]:
            return False

    return True
