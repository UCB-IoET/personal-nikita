"""
pysvcd demo: Subscribes to anything and everything it finds
"""

import time
from pysvcd import SerialSVCD, TimeoutException
from copy import deepcopy
import sys

def pprint(table):
    for k, v in table.items():
        print repr(k), ": {"
        for kk, vv in v.items():
            print "  ", repr(kk), ": {"
            for kkk, vvv in vv.items():
                print "  ", "  ", repr(kkk), ":", type(vvv)
            print "  ", "}"
        print "}"

subscriptions = set()
svcd = SerialSVCD()
try:
    time.sleep(5.0)
    last_table = {}
    i = 0
    while True:
        i += 1
        periodic = (i % 20) == 0

        table = svcd.get_table()

        do_print= False
        if table.keys() != last_table.keys():
            do_print = True
        else:
            for k,v in table.items():
                if v.keys() != last_table[k].keys():
                    do_print = True
                    break
                for kk, vv in v.items():
                    if vv.keys() != last_table[k][kk].keys():
                        do_print = True
                        break
        if do_print:
            pprint(table)
            last_table = deepcopy(table)

        for id in table:
            for svcid in table[id]:
                for attrid in table[id][svcid]:
                    if ((id, svcid, attrid) not in subscriptions) or periodic:
                        subscriptions.add((id, svcid, attrid))
                        def temp(id, svcid, attrid):
                            def printer(val):
                                print "{}:{}:{} = {}".format(id, svcid, attrid, val)
                            try:
                                table[id][svcid][attrid].subscribe(printer)
                            except TimeoutException:
                                pass
                        temp(id, svcid, attrid)
        time.sleep(1.0)
except KeyboardInterrupt:
    sys.exit(0)
