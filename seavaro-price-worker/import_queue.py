"""Import the authoritative SEAVARO queue from a private CSV file.
Never commit the source data or credentials to a public repository.
Usage: python seavaro-price-worker/import_queue.py /secure/path/queue.csv
"""
import csv,os,sys,re
import psycopg
def key(name):
 return re.sub(r"[^a-z0-9]","",name.casefold())
def run(path):
 with open(path,"r",encoding="utf-8-sig",newline="") as f:
  sniff=f.read(8192); f.seek(0)
  delimiter=";" if sniff.count(";")>=sniff.count(",") else ","
  reader=csv.DictReader(f,delimiter=delimiter)
  columns={key(k):k for k in reader.fieldnames or []}
  def col(*keys):
   for k in keys:
    if key(k) in columns:return columns[key(k)]
   return None
  sku_col=col("SKU","Osculati-SKU")
  ean_col=col("EAN")
  desc_col=col("Beschreibung","Description")
  if not sku_col:raise SystemExit("Missing SKU column: "+str(reader.fieldnames))
  if not os.environ.get("DATABASE_URL"):raise SystemExit("DATABASE_URL missing")
  imported=0;missing=0
  with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
   with conn.cursor() as c:
    c.execute("create table if not exists product_queue(sku text primary key,ean text,description text,status text default 'OPEN',attempts int default 0,last_error text,updated_at timestamptz)")
    for row in reader:
     sku=(row.get(sku_col) or "").strip()
     if not sku: missing+=1; continue
     ean=(row.get(ean_col) or "").strip() if ean_col else ""
     description=(row.get(desc_col) or "").strip() if desc_col else ""
     c.execute("""insert into product_queue(sku,ean,description)
     values (%s,%s,%s) on conflict (sku) do update set
     ean=case when excluded.ean<>'' then excluded.ean else product_queue.ean end,
     description=case when excluded.description<>'' then excluded.description else product_queue.description end
     """,(sku,ean,description))
     imported+=1
  print(f"Queue imported/upserted: {imported} rows; blank SKU: {missing}")
if __name__=="__main__":
 if len(sys.argv)!=2:raise SystemExit("Usage: python import_queue.py input.csv")
 run(sys.argv[1])
