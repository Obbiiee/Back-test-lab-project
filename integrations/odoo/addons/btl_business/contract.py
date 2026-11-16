"""Bounded sandbox business projection; no execution, entitlement or tax authority."""
import hashlib,json,re,uuid
MAX_BYTES=2097152
PHASES=('CREATED','CHECKOUT_STARTED','PENDING','FAILED','PAID','REVERSED','HOLD')
def need(ok):
    if not ok:raise ValueError('BUSINESS_PROJECTION_INVALID')
def uid(value):
    need(type(value) is str)
    try:need(str(uuid.UUID(value))==value)
    except (ValueError,AttributeError):raise ValueError('BUSINESS_PROJECTION_INVALID') from None
    return value
def decode(raw):
    need(type(raw) is bytes and len(raw)<=MAX_BYTES)
    def pairs(items):
        result={}
        for key,value in items:need(key not in result);result[key]=value
        return result
    value=json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:need(False))
    need(type(value) is dict and set(value)=={'schemaVersion','artifact','source','mode','customers','orders'})
    need(type(value['schemaVersion']) is int and value['schemaVersion']==1 and value['artifact']=='BTL-BUSINESS-EXPORT-1' and value['mode']=='SANDBOX')
    uid(value['source'])
    need(type(value['customers']) is list and type(value['orders']) is list and len(value['customers'])<=1000 and len(value['orders'])<=1000)
    accounts=set();orders=set()
    for customer in value['customers']:
        need(type(customer) is dict and set(customer)=={'id','email'})
        uid(customer['id']);email=customer['email']
        need(customer['id'] not in accounts and type(email) is str and 3<=len(email)<=320 and '@' in email and all(ord(c)>=32 for c in email))
        accounts.add(customer['id'])
    for order in value['orders']:
        need(type(order) is dict and set(order)=={'id','account','plan','amountIdr','phase','revision','expiresAt'})
        need(type(order['id']) is str and re.fullmatch(r'btl-sbx-[0-9a-f]{32}',order['id']) and order['id'] not in orders)
        need(order['account'] in accounts and type(order['plan']) is str and 1<=len(order['plan'])<=128)
        amount=order['amountIdr'];need(type(amount) is str and re.fullmatch(r'[1-9][0-9]{0,9}',amount) and int(amount)<=1000000000)
        need(order['phase'] in PHASES and type(order['revision']) is int and 0<=order['revision']<=2147483647)
        expiry=order['expiresAt'];need(expiry is None or type(expiry) is str and re.fullmatch(r'[0-9]{1,12}',expiry))
        need(order['phase']!='PAID' or expiry is not None)
        orders.add(order['id'])
    return value
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()


def sync_decode(raw):
    from datetime import datetime
    need(type(raw) is bytes and len(raw)<=8388608)
    def pairs(items):
        out={}
        for key,value in items:need(key not in out);out[key]=value
        return out
    value=json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:need(False))
    need(type(value) is dict and set(value)=={'schemaVersion','artifact','source','observedAtUs','snapshot','tickets'})
    need(type(value['schemaVersion']) is int and value['schemaVersion']==1 and value['artifact']=='BTL-BUSINESS-SYNC-1')
    uid(value['source']);need(type(value['observedAtUs']) is str and re.fullmatch(r'[1-9][0-9]{0,17}',value['observedAtUs']))
    snapshot=decode(json.dumps(value['snapshot'],ensure_ascii=True).encode());need(snapshot['source']==value['source'])
    accounts={x['id'] for x in snapshot['customers']};seen=set()
    need(type(value['tickets']) is list and len(value['tickets'])<=1000)
    for ticket in value['tickets']:
        need(type(ticket) is dict and set(ticket)=={'id','account','title','message','createdAt'})
        uid(ticket['id']);uid(ticket['account']);need(ticket['id'] not in seen and ticket['account'] in accounts);seen.add(ticket['id'])
        for key,limit in (('title',160),('message',4000)):
            text=ticket[key];need(type(text) is str and 1<=len(text.strip())<=limit and len(text)<=limit and all(c in '\n\t' or 32<=ord(c) and not 0xd800<=ord(c)<=0xdfff for c in text))
        need(type(ticket['createdAt']) is str and len(ticket['createdAt'])<=40)
        when=datetime.fromisoformat(ticket['createdAt']);need(when.tzinfo is not None and when.utcoffset().total_seconds()==0)
    return value
