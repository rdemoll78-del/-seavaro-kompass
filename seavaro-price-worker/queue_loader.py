import os,base64,gzip,csv,io
def load_private_queue(cursor):
    chunks=[(key,value) for key,value in os.environ.items() if key.startswith("SEAVARO_QUEUE_GZ_")]
    if not chunks:
        print("QUEUE_NOT_CONFIGURED",flush=True)
        return 0
    payload="".join(value for key,value in sorted(chunks))
    raw=gzip.decompress(base64.b64decode(payload)).decode("utf-8")
    reader=csv.reader(io.StringIO(raw),delimiter=";")
    total=0
    for row in reader:
        if len(row)<3: continue
        sku,ean,description=row[:3]
        if not sku: continue
        cursor.execute("insert into product_queue(sku,ean,description) values (%s,%s,%s) on conflict(sku) do update set ean=excluded.ean, description=excluded.description",(sku,ean,description))
        total+=1
    print("QUEUE_IMPORTED",total,flush=True)
    return total
