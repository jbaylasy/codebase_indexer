import sys
from datetime import datetime


def log(msg, **kwargs):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", **kwargs)
