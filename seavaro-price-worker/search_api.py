"""Structured provider search; no API requests are made without a configured key."""
import os,re,requests
from urllib.parse import urlsplit
def lookup(query, sku='', ean=''):
    key=os.environ.get('BRAVE_SEARCH_API_KEY','').strip()
    if not key:return []
    response=requests.get('https://api.search.brave.com/res/v1/web/search',
        params={'q':query,'count':10,'country':'DE','search_lang':'de'},
        headers={'X-Subscription-Token':key,'Accept':'application/json'},
        timeout=15)
    response.raise_for_status()
    out=[]
    for hit in response.json().get('web',{}).get('results',[]):
        url=hit.get('url','')
        text=' '.join((hit.get('title',''),hit.get('description',''),url)).lower()
        compact=re.sub('[^a-z0-9]','',text)
        exact_sku=re.sub('[^a-z0-9]','',sku.lower()) if sku else ''
        exact_ean=re.sub('[^a-z0-9]','',str(ean).lower()) if ean else ''
        if not ((exact_sku and exact_sku in compact) or (exact_ean and exact_ean in compact)):continue
        path=urlsplit(url).path.lower()
        if not url.startswith('https://') or not path.strip('/') or any(x in path for x in ('/brands/','/marke/','/marken/','/category/')):continue
        if url not in out:out.append(url)
    return out
