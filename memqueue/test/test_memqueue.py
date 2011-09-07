#!/usr/bin/env python
import unittest
import os
import sys
import memqueue


class MemQueueTest(unittest.TestCase):
    def setUp(self):
        self.mq = memqueue.MemQueue('[127.0.0.1:11211]')
        self.mq._mc.flush_all()

    def test_check_queue_not_exist(self):
        self.assertEquals(0, self.mq.check_queue("test1"))

    def test_check_queue_exist(self):
        self.mq.put("testQe","12345")
        self.assertNotEquals(0, self.mq.check_queue("testQe"))

    def test_create_clientID(self):
        c1 = self.mq.create_clientID()
        c2 = self.mq.create_clientID()
        self.assertNotEquals(c1,c2)

    def test_get_last_msg(self):
        for i in range(1,100):
            self.mq.put("testQ1",i)

        self.assertEquals(99, self.mq.last("testQ1"))

    def test_delete_msg(self):
        msgid=""
        for i in range(1,100):
            msgid = self.mq.put("testQ2", i)

        self.mq.delete("testQ2",msgid)
        self.assertEquals(None, self.mq.get("testQ2",msgid))

    def test_list_msg(self):
        for i in range(1,100):
            self.mq.put("testQ3", i)

        msglist = self.mq.listmsgs("testQ3")
        self.assertEquals(99, len(msglist))

    def test_next_msg1(self):
        msgid=""
        for i in range(1,50):
            msgid = self.mq.put("testQ4", i)

        for i in range(50,100):
            self.mq.put("testQ4", i)

        self.mq.get("testQ4",msgid)
        self.assertEquals(50, self.mq.nextmsg("testQ4"))

    def test_next_msg2(self):
        msgid=""
        for i in range(1,50):
            msgid = self.mq.put("testQ5", i)
            self.mq.get("testQ5", msgid)

        for i in range(50,100):
            self.mq.put("testQ5", i)

        self.assertEquals(50, self.mq.nextmsg("testQ5"))

    def test_next_msg3(self):
        msgid=""
        for i in range(1,50):
            msgid = self.mq.put("testQ6", i)
            self.mq.get("testQ6", msgid)

        for i in range(50,100):
            self.mq.put("testQ6", i)

        self.assertEquals(1, self.mq.nextmsg("testQ6","TestClient6"))

if __name__ == '__main__':
    unittest.main()
