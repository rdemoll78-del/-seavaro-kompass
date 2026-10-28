"""SEAVARO continuous worker: starts a research cycle every 30 seconds.

Run as a persistent Render background worker, not as a cron job.
It performs work; it does not create ChatGPT conversation turns.
"""
import os
import time
import signal
from worker import run

INTERVAL_SECONDS = 30
STOP = False

def stop(_signal, _frame):
    global STOP
    STOP = True

signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)

def main():
    if os.environ.get("SEAVARO_RUN_SECONDS", "155") == "0":
        print("SEAVARO_DISABLED", flush=True)
        return
    print("SEAVARO_CONTINUOUS_STARTED interval=30s", flush=True)
    while not STOP:
        started = time.monotonic()
        try:
            count = run()
            print("SEAVARO_CYCLE_COMPLETE processed=" + str(count), flush=True)
        except Exception as exc:
            print("SEAVARO_CYCLE_ERROR " + type(exc).__name__ + " " + str(exc)[:300], flush=True)
        # No overlapping cycles: schedule next cycle at least 30s after start.
        remaining = max(0, INTERVAL_SECONDS - (time.monotonic() - started))
        while remaining > 0 and not STOP:
            time.sleep(min(1, remaining))
            remaining = max(0, INTERVAL_SECONDS - (time.monotonic() - started))
    print("SEAVARO_CONTINUOUS_STOPPED", flush=True)

if __name__ == "__main__":
    main()
