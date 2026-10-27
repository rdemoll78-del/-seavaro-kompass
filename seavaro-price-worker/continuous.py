"""Continuous SEAVARO queue worker. Start only in a dedicated always-on Render service.
Requires DATABASE_URL. Never logs database credentials. No provider fees without configured API key.
"""
import os,time,signal,sys
from worker import run
stopping=False
def stop(*_):
 global stopping
 stopping=True
signal.signal(signal.SIGTERM,stop)
signal.signal(signal.SIGINT,stop)
def main():
 if not os.environ.get("DATABASE_URL"):
  print("CONFIG_REQUIRED_DATABASE_URL",flush=True)
  sys.exit(2)
 print("SEAVARO_CONTINUOUS_STARTED",flush=True)
 while not stopping:
  try:
   n=run()
   if n<0:
    # Another worker holds the database lock; retry after its lease ends.
    time.sleep(30)
   elif n==0:
    print("SEAVARO_QUEUE_OPEN_EMPTY_REVIEW_ITEMS_REMAIN",flush=True)
    time.sleep(180)
   else:
    print("SEAVARO_BATCH_COMPLETE",n,flush=True)
    time.sleep(2)
  except Exception as exc:
   print("SEAVARO_CONTINUOUS_ERROR",type(exc).__name__,str(exc)[:240],flush=True)
   time.sleep(30)
 print("SEAVARO_CONTINUOUS_STOPPED",flush=True)
if __name__=="__main__":main()
