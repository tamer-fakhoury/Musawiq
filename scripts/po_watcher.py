# PO watcher - file-based trigger
import json, time, os, subprocess
from pathlib import Path

TRIGGER = Path('var/po_check_trigger.txt')
REPO = Path('.')
CFG = Path('scripts/po_config.json')

def review():
    try:
        r = subprocess.run(['git', 'log', '--oneline', '-10'], cwd=str(REPO), stdout=subprocess.PIPE)
        print(r.stdout.decode())
    except Exception as e:
        print('err', e)

if __name__ == '__main__':
    TRIGGER.parent.mkdir(exist_ok=True)
    if not TRIGGER.exists():
        TRIGGER.write_text(str(time.time()))
    last = TRIGGER.stat().st_mtime
    while True:
        try:
            st = TRIGGER.stat().st_mtime
            if st != last:
                last = st
                print('TRIGGERED - checking engineers')
                review()
        except Exception:
            pass
        time.sleep(30)
