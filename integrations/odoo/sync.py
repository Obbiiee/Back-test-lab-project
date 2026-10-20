"""One-shot scheduled business projection; errors never print payloads or secrets."""
import json,os,sys
from urllib.parse import urlsplit
import httpx
from export import bundle

def push(raw,url,database,key,company,*,transport=None):
    parsed=urlsplit(url)
    if parsed.scheme not in ('https','http') or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ('','/') or parsed.query or parsed.fragment or parsed.scheme=='http' and parsed.hostname not in ('127.0.0.1','localhost','::1'):
        raise ValueError('ODOO_DESTINATION_REFUSED')
    if not isinstance(database,str) or not database or len(database)>63 or not isinstance(key,str) or len(key)<32 or type(company) is not int or company<1 or len(raw)>8388608:raise ValueError('ODOO_CONFIG_REFUSED')
    # No redirects, proxy env, blind HTTP retries or unbounded response buffering.
    with httpx.Client(timeout=httpx.Timeout(15,connect=5),follow_redirects=False,trust_env=False,transport=transport) as client:
        with client.stream('POST',url.rstrip('/')+'/json/2/btl.import.batch/sync_bundle',headers={'Authorization':'Bearer '+key,'X-Odoo-Database':database},json={'bundle':raw.decode('utf-8'),'company_id':company}) as response:
            data=bytearray()
            for part in response.iter_bytes():
                data.extend(part)
                if len(data)>16384:raise ValueError('ODOO_RESPONSE_LIMIT')
            if response.status_code!=200:raise ValueError('ODOO_SYNC_REFUSED')
            result=json.loads(data)
            if type(result) is not dict or set(result)!={'accepted','customers','payments','tickets'} or result['accepted'] is not True or any(type(result[k]) is not int or not 0<=result[k]<=1000 for k in ('customers','payments','tickets')):raise ValueError('ODOO_RESPONSE_REFUSED')
            return result

def main():
    try:
        result=push(bundle(os.environ['BTL_BUSINESS_EXPORT_DSN'],os.environ['BTL_BUSINESS_SOURCE']),os.environ['BTL_ODOO_URL'],os.environ['BTL_ODOO_DATABASE'],os.environ['BTL_ODOO_API_KEY'],int(os.environ['BTL_ODOO_COMPANY']))
    except Exception:
        print('ODOO_SYNC_FAILED_SAFE_TO_RETRY_NEXT_SCHEDULE',file=sys.stderr);return 1
    print(json.dumps(result));return 0
if __name__=='__main__':raise SystemExit(main())
