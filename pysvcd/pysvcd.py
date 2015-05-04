import stormloader
import time
import msgpack
import sys
import re
import threading
import json
from Queue import Queue, Empty
from collections import namedtuple

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
            for tries in range(10):
                try:
                    item = self.return_queue.get(True, 5.0)
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
                    def attr_write(payload, timeout_ms):
                        return self.write(ip, kk, attr, payload, timeout_ms)
                    def attr_subscribe(on_notify):
                        return self.subscribe(ip, kk, attr, on_notify)
                    subtable[strkk][strattr] = SVCDObject(write=attr_write,
                                                          subscribe=attr_subscribe)
            table[k] = subtable
        return table

    def __on_notify(self, event):
        ivkid = event["ivkid"]
        val = event["val"]

        if ivkid in self.notifiers:
            self.notifiers[ivkid](val)

    def __on_advert_received(self, event):
        try:
            srcip = event["srcip"]
            pay = msgpack.unpackb(event["pay"])
            srcport = event["srcport"]
        except: # Failed to parse
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
        obj = {
            "name": "SVCD.write",
            "targetip": targetip,
            "svcid": svcid,
            "attrid": attrid,
            "payload": payload,
            "timeout_ms": timeout_ms
        }

        obj = self.bridge.do_task(obj, block=True)
        return obj["code"]

    def subscribe(self, targetip, svcid, attrid, on_notify):
        obj = {
            "name": "SVCD.subscribe",
            "targetip": targetip,
            "svcid": svcid,
            "attrid": attrid,
            "callback_id": "dummy",
        }

        ivkid = self.bridge.do_task(obj, block=True)["ivkid"]

        self.notifiers[ivkid] = on_notify

        def unsubscribe_fn():
            self.__unsubscribe(targetip, svcid, attrid, ivkid)

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