import stormloader
import time
import msgpack
import sys
import re
import threading
import json
from Queue import Queue, Empty
from collections import namedtuple
import struct

# Code for packing/unpacking the SVCD formats
unpackers = {
                "u8": lambda s: (struct.unpack("b", s[0])[0], s[1:]),
                "s8": lambda s: (struct.unpack("B", s[0])[0], s[1:]),
                "u16": lambda s: (struct.unpack("h", s[0:2])[0], s[2:]),
                "s16": lambda s: (struct.unpack("H", s[0:2])[0], s[2:]),
                "pstr": lambda s: (s[1:ord(s[0])+1], s[ord(s[0])+1:]),
    }

packers = {
                "u8": lambda val: (struct.pack("b", val)),
                "s8": lambda val: (struct.pack("B", val)),
                "u16": lambda val: (struct.pack("h", val)),
                "s16": lambda val: (struct.pack("H", val)),
                "pstr": lambda val: (chr(len(val)) + val),
    }

def svcd_unpack(val, format):
    res = []
    for type in format:
        subval, val = unpackers[type](val)
        res.append(subval)

    if len(res) == 1:
        return res[0]
    else:
        return tuple(res)

def svcd_pack(val, format):
    if type(val) in (int, float, str):
        val = [val]
    res = ""
    for subval, tp in zip(val, format):
        res += packers[tp](subval)
    return res

assert svcd_unpack(svcd_pack(5, ['u16']), ['u16']) == 5

class TimeoutException(Exception):
    pass

SVCDObject = namedtuple('SVCDObject', ['write', 'subscribe'])

class SerialBridge(object):
    def __init__(self):
        self.active = False
        self.task_queue = Queue()
        self.return_queue = Queue()
        self.event_handlers = {}
        self.callback_id = 0

        self.thread = threading.Thread(target=self.run_bridge)
        self.thread.daemon = True

    def start(self):
        self.active = True
        self.thread.start()

    def stop(self):
        self.active = False
        self.thread.join()

        # Empty out the queues
        try:
            while True:
                self.task_queue.get_nowait()
        except Queue.Empty:
            pass
        try:
            while True:
                self.return_queue.get_nowait()
        except Queue.Empty:
            pass

        # Destroy all event handlers
        self.event_handlers = {}

    def on_event(self, name, handler):
        self.event_handlers[name] = handler

    def do_task(self, obj, block=False):
        if block:
            my_callback_id = self.callback_id
            self.callback_id += 1
            obj["callback_id"] = my_callback_id
        self.task_queue.put(obj)

        if block:
            for tries in range(5):
                try:
                    if tries == 0:
                        item = self.return_queue.get(True, 0.7)
                    else:
                        item = self.return_queue.get(True, 0.1)
                except Empty:
                    raise TimeoutException
                if "callback_id" in item and item["callback_id"] == my_callback_id:
                    return item
                else:
                    time.sleep(0.01)
                    self.return_queue.put(item)
            raise TimeoutException

    def run_bridge(self):
        self.sl = stormloader.sl_api.StormLoader(None)
        no_reset = False
        if not no_reset:
            self.sl.enter_payload_mode()
        print "[SLOADER] Attached"

        full_match = re.compile("PACKED<[0-f]+>")
        partial_match = re.compile("P(A(C(K(E(D(<([0-f]+(>)?)?)?)?)?)?)?)?$")
        read_buf = ""
        num = 0
        while self.active:
            try:
                task = self.task_queue.get_nowait()
                self.print_packed(task)
            except Empty:
                pass

            c = self.sl.raw_read_noblock_buffer()
            if len(c) > 0:
                # sys.stdout.write(c)
                # sys.stdout.flush()

                read_buf += c
                # Remove any complete matches from the buffer
                while True:
                    m = full_match.search(read_buf)
                    if m:
                        self.parse_packed(read_buf[m.start():m.end()])
                        read_buf = read_buf[:m.start()] + read_buf[m.end():]
                    else:
                        break

            # Print anything that is not a partial match
            m = partial_match.search(read_buf)
            if m:
                if read_buf[:m.start()].strip() != "":
                    sys.stdout.write(read_buf[:m.start()])
                    sys.stdout.flush()
                read_buf = read_buf[m.start():m.end()]

    def print_packed(self, obj):
        obj = msgpack.packb(obj)
        try:
            self.sl.raw_write(obj + "SUBMIT\n")
        except IOError:
            pass

    def parse_packed(self, s):
        m = re.match("PACKED<([0-f]+)>", s)
        if not m:
            print "WARNING, should not happen"
        vals = iter(m.group(1))
        vals = [ chr(int(a + b, 16)) for a, b in zip(vals, vals)]
        self.dispatch(msgpack.unpackb("".join(vals)))

    def dispatch(self, event):
        if "callback_id" in event:
            self.return_queue.put(event)
        elif "name" in event and event["name"] in self.event_handlers:
            self.event_handlers[event["name"]](event)
        else:
            print "Discarding event", event

class SerialSVCD(object):
    OK = 1
    TIMEOUT = 2

    def __init__(self):
        self.notifiers = {}

        self.bridge = SerialBridge()
        self.bridge.on_event("notify", self.__on_notify)
        self.bridge.on_event("advert_received", self.__on_advert_received)

        self.service_ips = {}
        self.service_table = {}

        with open("manifest.json") as f:
            self.manifest = json.load(f)


        self.bridge.start()

    def stop(self):
        self.bridge.stop()

    def get_service_info(self, svc):
        svc = self.get_service_name(svc)
        if svc in self.manifest:
            return self.manifest[svc]
        else:
            return None

    def get_attribute_info(self, svc, attr):
        svc = self.get_service_name(svc)
        attr = self.get_attribute_name(svc, attr)
        try:
            return self.manifest[svc]["attributes"][attr]
        except KeyError:
            return None

    def get_service_name(self, svc):
        for k, v in self.manifest.items():
            if int(v['id'], 16) == svc:
                return k
        return str(svc)

    def get_attribute_name(self, svc, attr):
        if type(svc) is not str:
            svc = self.get_service_name(svc)

        if svc not in self.manifest:
            return str(attr)

        for k, v in self.manifest[svc]["attributes"].items():
            if int(v['id'], 16) == attr:
                return k
        return str(attr)

    def get_table(self):
        table = {}
        for k, v in self.service_table.items():
            ip = self.service_ips[k]
            subtable = {}
            for kk, vv in self.service_table[k].items():
                strkk = self.get_service_name(kk)
                subtable[strkk] = {}
                for attr in vv:
                    strattr = self.get_attribute_name(strkk, attr)
                    def temp(ip, kk, attr, strkk, strattr):
                        def attr_write(payload, timeout_ms):
                            return self.write(ip, kk, attr, payload, timeout_ms)
                        def attr_subscribe(on_notify):
                            return self.subscribe(ip, kk, attr, on_notify)
                        subtable[strkk][strattr] = SVCDObject(write=attr_write,
                                                              subscribe=attr_subscribe)
                    temp(ip, kk, attr, strkk, strattr)
            table[k] = subtable
        return table

    def __on_notify(self, event):
        ivkid = event["ivkid"]
        val = event["val"]

        print "notify", ivkid, val
        if ivkid in self.notifiers:
            self.notifiers[ivkid](val)

    def __on_advert_received(self, event):
        # print "got advert",
        try:
            srcip = event["srcip"]
            pay = msgpack.unpackb(event["pay"])
            srcport = event["srcport"]
            # print pay["id"] if "id" in pay else srcip, srcip
            # print pay
        except: # Failed to parse
            # print "unparsed"
            return

        if "id" in pay:
            id = pay["id"]
        else:
            id = str(srcip)

        if id in self.service_ips and self.service_ips[id] != srcip:
            del self.service_ips[id]
            del self.service_table[id]

        self.service_ips[id] = srcip
        if id not in self.service_table:
            self.service_table[id] = {}

        for svcid, svcval in pay.items():
            if svcid == "id":
                continue
            elif svcid not in self.service_table[id]:
                self.service_table[id][svcid] = sorted(set(svcval))
            else:
                self.service_table[id][svcid] = sorted(set(self.service_table[id][svcid]) | set(svcval))

    def write(self, targetip, svcid, attrid, payload, timeout_ms):
        info = self.get_attribute_info(svcid, attrid)
        if info is None or "format" not in info:
            val = payload
        else:
            format = [x[0] for x in info["format"]]
            val = svcd_pack(payload, format)

        obj = {
            "name": "SVCD.write",
            "targetip": targetip,
            "svcid": svcid,
            "attrid": attrid,
            "payload": val,
            "timeout_ms": timeout_ms
        }

        obj = self.bridge.do_task(obj, block=True)
        return obj["code"]

    def subscribe(self, targetip, svcid, attrid, on_notify):
        assert on_notify is not None
        obj = {
            "name": "SVCD.subscribe",
            "targetip": targetip,
            "svcid": svcid,
            "attrid": attrid,
            "callback_id": "dummy",
        }

        ivkid = self.bridge.do_task(obj, block=True)["ivkid"]

        info = self.get_attribute_info(svcid, attrid)
        if info is None or "format" not in info:
            wrapped_on_notify = on_notify
        else:
            format = [x[0] for x in info["format"]]
            def wrapped_on_notify(val):
                try:
                    on_notify(svcd_unpack(val, format))
                except:
                    print "WARNING: invalid value from", svcid, attrid

        self.notifiers[ivkid] = wrapped_on_notify

        def unsubscribe_fn():
            self.__unsubscribe(targetip, svcid, attrid, ivkid)

        print "subscribed", svcid, attrid, ivkid
        return unsubscribe_fn

    def __unsubscribe(self, targetip, svcid, attrid, ivkid):
        obj = {
            "name": "SVCD.unsubscribe",
            "targetip": targetip,
            "svcid": svcid,
            "attrid": attrid,
            "ivkid": ivkid
        }

        self.bridge.do_task(obj, block=True)

        del self.notifiers[ivkid]

