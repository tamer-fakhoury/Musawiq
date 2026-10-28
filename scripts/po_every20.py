import time
from datetime import datetime
from pathlib import Path
LOG = Path('var/po_notifications.log')
while True:
    LOG.parent.mkdir(parents=True,exist_ok=True)
    open(LOG,'a').write(datetime.now().isoformat() + ' CHECK_ENGINEERS
')
    time.sleep(1200)

