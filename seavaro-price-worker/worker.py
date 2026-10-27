import os,time,re,json,html,random,urllib.parse,datetime
import requests, psycopg
from bs4 import BeautifulSoup

DB=os.environ["DATABASE_URL"]
UA={"User-Agent":"Mozilla/5.0 (compatible; SEAVAROPriceResearch/1.0; commercial price comparison)"}
def db():
 return psycopg.connect(DB,connect_timeout=15,autocommit=True)
def init(c):
 c.execute("""create table if not exists product_queue(sku text primary key,ean text,description text,status text default 'OPEN',attempts int default 0,last_error text,updated_at timestamptz);""")
 c.execute("""create table if not exists offers(id bigserial primary key,sku text not null,merchant text,price numeric(12,2),currency text,unit text,url text not null,observed_at timestamptz default now(),evidence text,unique(sku,url,price));""")
 c.execute("""create table if not exists research_log(id bigserial primary key,sku text,at timestamptz default now(),status text,note text);""")
def request(url):
 r=requests.get(url,headers=UA,timeout=18,allow_redirects=True)
 r.raise_for_status()
 if len(r.content)>1500000: raise ValueError('too large')
 return r.text
def find_urls(q):
 urls=[]
 for endpoint in ['https://www.bing.com/search?q=','https://html.duckduckgo.com/html/?q=']:
  try:
   soup=BeautifulSoup(request(endpoint+urllib.parse.quote(q)),'html.parser')
   for a in soup.select('li.b_algo h2 a[href], a.result__a[href], a.result-link[href]'):
    href=a.get('href','')
    if href.startswith('/url?q='):href=urllib.parse.parse_qs(urllib.parse.urlsplit(href).query).get('q',[''])[0]
    if 'duckduckgo.com/l/' in href:
     href=urllib.parse.parse_qs(urllib.parse.urlsplit(href).query).get('uddg',[''])[0]
    if href.startswith('//'):href='https:'+href
    if not href.startswith('https://'):continue
    host=urllib.parse.urlparse(href).netloc.lower()
    if any(x in host for x in ('google.','bing.','duckduckgo.','youtube.','wikipedia.','facebook.','instagram.','amazonaws.','osculati.com')):continue
    if href not in urls:urls.append(href)
    if len(urls)>=18:return urls
  except Exception as e:print('SEARCH_ERROR',type(e).__name__,str(e)[:100],flush=True)
 return urls
def collect_schema(obj):
 if isinstance(obj,list):
  for x in obj:yield from collect_schema(x)
 elif isinstance(obj,dict):
  if obj.get('@type') in ('Product','IndividualProduct') or 'Product' in str(obj.get('@type','')):
   yield obj
  for v in obj.values():
   if isinstance(v,(dict,list)):yield from collect_schema(v)
def parse_offer(url,sku,ean):
 page=request(url)
 soup=BeautifulSoup(page,'html.parser')
 text=soup.get_text(' ',strip=True)
 digits=lambda s:re.sub('[^0-9A-Za-z]','',str(s)).lower()
 identifier=digits(ean) if ean else ''
 sku_normal=digits(sku)
 sku_on_page=sku.lower() in text.lower() or (sku_normal and sku_normal in digits(text))
 ean_on_page=bool(identifier and identifier in digits(text))
 if not (sku_on_page or ean_on_page):return None
 host=urllib.parse.urlsplit(url).netloc.lower()
 best=[]
 for tag in soup.select('script[type="application/ld+json"]'):
  try:
   for prod in collect_schema(json.loads(tag.string or tag.text or '{}')):
    identifiers=[str(prod.get(k,'')) for k in ('sku','gtin','gtin13','mpn')]
    if not (sku_on_page or ean_on_page or any(digits(x) in (sku_normal,identifier) for x in identifiers if x)):continue
    offers=prod.get('offers',[])
    for o in (offers if isinstance(offers,list) else [offers]):
     if not isinstance(o,dict):continue
     p=o.get('price') or o.get('lowPrice')
     cur=o.get('priceCurrency','')
     if p is not None and re.fullmatch(r'[0-9]+(?:[.,][0-9]{1,2})?',str(p)):
      price=float(str(p).replace(',','.'))
      if 0<price<1000000:best.append((price,cur,prod.get('name','')))
  except (ValueError,TypeError):continue
 if not best:return None
 price,cur,name=min(best)
 # JSON-LD offer is captured as candidate only. Currency/unit and exact variant need manual evidence verification.
 return dict(sku=sku,url=url,merchant=host,price=price,currency=cur or 'UNKNOWN',unit='UNKNOWN',evidence=('JSON-LD candidate; exact unit requires verification; '+str(name))[:500])
def run():
 with db() as conn:
  with conn.cursor() as c:
   init(c)
   from queue_loader import load_private_queue
   load_private_queue(c)
   print('QUEUE_READY',flush=True)
   # Avoid competing processes by PostgreSQL advisory lock
   c.execute('select pg_try_advisory_lock(9042726)')
   if not c.fetchone()[0]:
    print('Another run active');return
   c.execute("select sku,ean,description,attempts from product_queue where status in ('OPEN','RETRY') order by attempts,sku limit 4")
   batch=c.fetchall()
   c.execute('select status,count(*) from product_queue group by status order by status')
   print('QUEUE_STATUS',c.fetchall(),flush=True)
   for sku,ean,desc,attempts in batch:
    try:
     queries=[x for x in (ean,sku,desc) if x]
     print('RESEARCH_START',sku,'searches',len(queries),flush=True)
     sources=[]
     for q in queries:
      for url in find_urls('Osculati '+q):
       if url not in sources:sources.append(url)
     print('SEARCH_URLS',sku,len(sources),flush=True)
     print('SEARCH_STATS',sku,'urls',len(sources),'attempt',attempts+1,flush=True)
     count=0
     for url in sources[:20]:
      try:
       offer=parse_offer(url,sku,ean)
       if offer:
        c.execute('insert into offers(sku,merchant,price,currency,unit,url,evidence) values(%s,%s,%s,%s,%s,%s,%s) on conflict do nothing',(sku,offer['merchant'],offer['price'],offer['currency'],offer['unit'],url,offer['evidence']))
        count+=1
      except Exception as e:
       c.execute('insert into research_log(sku,status,note) values(%s,%s,%s)',(sku,'SOURCE_ERROR',(url+' '+str(e))[:700]))
     # No false assertion that no competitor exists; mark examined and preserve candidates
     status='CANDIDATES' if count else 'REVIEW_REQUIRED'
     c.execute('update product_queue set status=%s,attempts=attempts+1,updated_at=now(),last_error=null where sku=%s',(status,sku))
     c.execute('insert into research_log(sku,status,note) values(%s,%s,%s)',(sku,status,'sources='+str(len(sources))+' jsonld_candidates='+str(count)+'; not a conclusive no-competitor finding'))
     print(sku,status,count,flush=True)
    except Exception as e:
     c.execute('update product_queue set status=%s,attempts=attempts+1,last_error=%s,updated_at=now() where sku=%s',('ERROR',str(e)[:400],sku))
     print('ERROR',sku,str(e)[:120],flush=True)
     continue
   c.execute('select pg_advisory_unlock(9042726)')
if __name__=='__main__':
 # Continue processing batches in one job rather than exiting after four SKUs.
 deadline=time.monotonic()+int(os.environ.get("SEAVARO_RUN_SECONDS","3000"))
 while time.monotonic()<deadline:
  try:
   run()
  except Exception as exc:
   print("RUN_ERROR",type(exc).__name__,str(exc)[:250],flush=True)
   time.sleep(15)
  else:
   time.sleep(2)

