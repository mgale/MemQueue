#!/usr/bin/env python
#
# Copyright 2011
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

"""A utility class to read and write data to a queue in memcache."""

import errno
import logging
import memcache
import time
import uuid

version = "1.0git"
version_info = (1,0,0)

class MemQueue(object):
    """ Returns a MemQueue object

    The following keys exist for each Q:
    QNAME_LIST_<TIMESTAMP>: Contains a comman separated list of entries
    QNAME_LASTMSG: Contains the last message
    QNAME_LASTMSG_<clientID>: The ID of the last message for this client

    """

    DEFAULT_CLIENTID = "UnknownClient"

    def __init__(self, primaryservers, backupservers=None,
        autodelete=False, clientlag=120 ):
        """ Create a MemQueue Object

        @param primaryservers: List of memcache servers
        @param backupservers: List of backup memcache servers to provide
                redundancy. Data will be mirrored across the primary and
                backup. **** NOT IMPLEMENTED ****
        @param autodelete: If enabled, messages will be auto deleted after
                a get request is made. Default if False.
        @param clientlag: How long a client can lag behind in msgs, if a
                client is move than X seconds behind then calling next
                will return the last message in the queue.

        Queues are created as needed.
        """

        self._mc = memcache.Client(['127.0.0.1:11211'])
        self._autodelete = autodelete
        self._clientlag = clientlag

    def purge_queue(self, mqname, tframe=30, clientID=DEFAULT_CLIENTID):
        """ Delete a queue

        @param mqname: Name of queue to create
        @param tframe: The time frame to purge the queue for.
        @param clientID: Unique ID of client
        """

        delkeys = self._get_timecache_key(mqname, tframe)

        for k in delkeys:
            self.delete(mqname, k, clientID)


    def listmsgs(self, mqname, tframe=10, clientID=DEFAULT_CLIENTID):
        """ List messages in a queue

        @param mqname: name of queue
        @param tframe: The time frame of the view, by default we show the last
                10 minutes. Since the view of the queue is best effort.
        @param clientID: Unique ID of client (socket address, UUID, etc)
        @return: A list a keys that point to messages
        """

        msgs = []

        lkeys = self._get_timecache_keys(mqname, tframe)
        for k in lkeys:
            msg_list = self._mc.get(k)
            if msg_list:
                msgs.extend(msg_list.split(","))

        #Pop off the last empty entry
        msgs.pop()
        return msgs


    def put(self, mqname, data, clientID=DEFAULT_CLIENTID):
        """ Put a message in the queue

        @param mqname: name of queue
        @param data: The data you want to store in the queue, should be less
                than 1 MB. Unless you alter your memcache configuration.
        @param clientID: Unique ID of client (socket address, UUID, etc)
        @return: The memcache key that the messsage was stored under
        """

        msginfo = "%s_%s"%(clientID, time.time())
        msgUID = uuid.uuid4()
        keyID = "%s_%s_%s"%(mqname, msginfo, msgUID)
        self._mc.set(keyID, data)

        self._set_last_msg(mqname, keyID, clientID)
        self._update_cache_view(mqname, keyID)

        return keyID

    def get(self, mqname, keyID, clientID=DEFAULT_CLIENTID ):
        """ Get a message from the queue

        @param mqname: name of queue
        @param keyID: The key returned from put or list, identifies your
                message.
        @param clientID: Unique ID of client (socket address, UUID, etc)
        @return: The data with in the message
        """

        data = self._mc.get(keyID)

        if (self._autodelete):
            self.delete(mqname, keyID, clientID)

        self._set_last_client(mqname, clientID, keyID)

        return data

    def last(self, mqname, clientID=DEFAULT_CLIENTID ):
        """ Get the last message from the queue

        @return: The data with in the message
        @param mqname: name of queue
        @param clientID: Unique ID of client (socket address, UUID, etc)
        @return: The data with in the message
        """

        keyID = self._get_last_msg(mqname, clientID)

        return self.get(mqname, keyID, clientID)


    def delete(self, mqname, keyID, clientID=DEFAULT_CLIENTID):
        """ Delete a message from the queue

        @return: The data with in the message
        @param mqname: name of queue
        @param keyID: The key returned from put or list, identifies your
                message.
        """

        return self._mc.delete(keyID)

    def create_clientID(self):
        """ Returns a unique ID that can identify a client.

        @return: UUID of a client

        There are no controls or authentication around clients, the
        methode is currently available to aid in indentifing clients.

        For example the puts and gets can take a clientID, so the calling app
        needs to provide this.
        """

        return  uuid.uuid1()

    def nextmsg(self, mqname, clientID=DEFAULT_CLIENTID):
        """ Get the next message in the queue

        @param mqname: Name of the queue.
        @param clientID: The clientID
        @return: The next message for the client or none if no new messages
            exist.
        """

        index_of_lastmsg = 0

        lastclientmsg, lastclienttime = self._get_last_client(
            mqname, clientID)
        lastmsg = self._get_last_msg(mqname, clientID)

        if (lastclientmsg == lastmsg):
            return None

        if ( lastclienttime and lastclienttime < (time.time() - self._clientlag)):
            return self.last(mqname, clientID)

        msgs = self.listmsgs(mqname, self._clientlag, clientID)
        try:
            index_of_lastmsg = msgs.index(lastclientmsg)
            index_of_lastmsg+=1
        except ValueError:
            index_of_lastmsg = 0

        return self.get(mqname, msgs.pop(index_of_lastmsg), clientID)


    def _get_timecache_keys(self, mqname, tframe):
        """ Return the view format

        @return: List of keys that could contain data for the queue
        @param mqname: name of queue
        @param tframe: Time size of queue to see in minutes
        """

        keylist = []
        Q_FORMAT="%Y%m%d%H%M"
        ts = time.strftime("%s"%(Q_FORMAT))
        start_time = int(ts) - int(tframe)

        for i in range(start_time, (int(ts)+1)):
            keyID = "%s_%s_%s"%(mqname, "LIST", i)
            keylist.append(keyID)

        return keylist

    def _update_cache_view(self, mqname, keyID):
        """ Update the view of the cache

        @return: Result of adding the key
        @param mqname: name of queue
        @param keyID: The keyID of the message that was added
        """

        keylist = self._get_timecache_keys(mqname, 1)
        keynow = keylist.pop()

        append_value = "%s,"%(keyID)

        if ( not self._mc.append(keynow, append_value) ):
            if  ( not self._mc.add(keynow, append_value) ):
                self._mc.append(keynow, append_value)

        return self._mc.set("%s"%(mqname),time.time())

    def _set_last_msg(self, mqname, keyID, clientID):
        """ Update the last message property """

        self._mc.set("%s_LASTMSG"%(mqname), keyID)


    def _get_last_msg(self, mqname, clientID):
        """ Get the last message property """

        return self._mc.get("%s_LASTMSG"%(mqname))

    def check_queue(self, mqname):
        """ Check a queue

        @param mqname: Name of queue to check
        @return: Zero if it does not exist, nonzero otherwise.
        """

        cq = self._mc.get("%s"%(mqname))

        if cq is None:
            return 0
        else:
            return cq

    def _set_last_client(self, mqname, clientID, keyID):
        """ Update client meta data

        @param mqname: Name of the queue
        @param clientID: Client Identifier
        @param keyID: memcache key
        """

        self._mc.set("%s_LASTMSG_%s"%(mqname, clientID), keyID)
        self._mc.set("%s_LASTTIME_%s"%(mqname, clientID), time.time())

    def _get_last_client(self, mqname, clientID):
        """ Return client meta data

        @param mqname: Name of the queue
        @param clientID: Client Identifier
        @return: List of (lastmsg, timestamp)
        """

        lastmsg = self._mc.get("%s_LASTMSG_%s"%(mqname, clientID))
        lasttime = self._mc.get("%s_LASTTIME_%s"%(mqname, clientID))
        return [lastmsg,lasttime]
