# PO scheduler - sends Check Engineers every 20 min and reviews work
import json, time, urllib.request
from pathlib import Path

CFG = Path('scripts/po_config.json')
INTERVAL = 1200

def check():
    try:
        cfg = json.loads(CFG.read_text())
        # trigger a check via notify or just log
        try:
            body = json.dumps({'msg':'Check Engineers'}).encode()
            req = urllib.request.Request('http://localhost:5555/notify', data=body, method='POST', headers={'Content-Type':'application/json'})
            urllib.request.urlopen(req, timeout=5)
        except:
            pass
    except:
        pass

if __name__=='__main__':
    while True:
        check()
        time.sleep(INTERVAL)
