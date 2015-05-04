"""
pysvcd demo: Subscribes to anything and everything it finds
"""

import time
from pysvcd import SerialSVCD
import sys

subscriptions = set()
svcd = SerialSVCD()
try:
    time.sleep(5.0)
    last_keys = set([None])
    while True:
        table = svcd.get_table()
        if set(table.keys()) != last_keys:
            print table
            last_keys = set(table.keys())

        for id in table:
            for svcid in table[id]:
                for attrid in table[id][svcid]:
                    if (id, svcid, attrid) not in subscriptions:
                        subscriptions.add((id, svcid, attrid))
                        def printer(val):
                            print "{}:{}:{} = {}".format(id, svcid, attrid, val)
                        table[id][svcid][attrid].subscribe(printer)
        time.sleep(1.0)
except KeyboardInterrupt:
    sys.exit(0)
