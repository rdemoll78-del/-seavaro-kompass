import os,csv,io
def load_private_queue(cursor):
    chunks=sorted((key,value) for key,value in os.environ.items() if key.startswith("SEAVARO_QUEUE_PART_"))
    if not chunks:
        print("QUEUE_NOT_CONFIGURED",flush=True)
        return 0
    total=0
    for key,chunk in chunks:
        for row in csv.reader(io.StringIO(chunk),delimiter="|"):
            if len(row)<3: continue
            sku,ean,description=row[:3]
            if not sku: continue
            cursor.execute("insert into product_queue(sku,ean,description) values (%s,%s,%s) on conflict(sku) do update set ean=excluded.ean,description=excluded.description",(sku,ean,description))
            total+=1
    print("QUEUE_IMPORTED",total,flush=True)
    return total
