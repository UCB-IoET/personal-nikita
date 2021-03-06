"""
pysvcd demo: Actuates any coffee makers it finds
"""

import time
from pysvcd import SerialSVCD
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

svcd = SerialSVCD()
try:
    time.sleep(5.0)
    last_keys = set([None])
    while True:
        table = svcd.get_table()
        if set(table.keys()) != last_keys:
            pprint(table)
            last_keys = set(table.keys())
        try:
            x = table["coffee"][u'pm.storm.svc.nespresso'][u'pm.storm.attr.nespresso.mkcoffee']
        except:
            x = None

        if x:
            try:
                print "writing...", x.write(5, timeout_ms=1000)
            except:
                print "write failed"
                raise
            time.sleep(2.0)
        time.sleep(1.0)
except KeyboardInterrupt:
    sys.exit(0)
