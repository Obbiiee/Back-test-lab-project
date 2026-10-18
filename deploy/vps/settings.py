"""Strict file-only deployment settings. Exceptions contain codes, never values."""
import json,re
from pathlib import Path
from psycopg.conninfo import conninfo_to_dict

class ConfigurationError(ValueError):pass

def need(condition,code):
    if not condition:raise ConfigurationError(code)

def read_json(path):
    p=Path(path);need(0<p.stat().st_size<=16384,'SECRET_FILE_SIZE')
    def unique(pairs):
        out={}
        for key,value in pairs:need(key not in out,'DUPLICATE_CONFIG_KEY');out[key]=value
        return out
    try:value=json.loads(p.read_text(encoding='utf-8'),object_pairs_hook=unique)
    except (UnicodeError,json.JSONDecodeError):raise ConfigurationError('CONFIG_JSON') from None
    need(type(value) is dict,'CONFIG_OBJECT');return value

def connection(value,user):
    need(type(value) is str and value and 'REPLACE' not in value,'DATABASE_CONFIG')
    try:fields=conninfo_to_dict(value)
    except Exception:raise ConfigurationError('DATABASE_CONFIG') from None
    need(fields.get('host')=='db' and fields.get('dbname')=='btl' and fields.get('user')==user and bool(fields.get('password')),'DATABASE_IDENTITY')
    need(set(fields)<=set(('host','dbname','user','password','port','sslmode','connect_timeout')),'DATABASE_OPTIONS')
    need(fields.get('port','5432')=='5432','DATABASE_PORT');return value

def runtime(value):
    required={'BTL_DATABASE_URL','BTL_AUTH_SECRET','BTL_SMTP_HOST','BTL_SMTP_USER','BTL_SMTP_PASSWORD','BTL_SMTP_SENDER','BTL_SANDBOX_V2_RESET_TIMEZONE'}
    optional={'BTL_GOOGLE_CLIENT_ID','BTL_GOOGLE_CLIENT_SECRET','BTL_GOOGLE_REDIRECT_URI'}
    need(required<=set(value)<=required|optional,'RUNTIME_CONFIG_KEYS')
    need(all(type(v) is str for v in value.values()),'CONFIG_STRING_VALUES')
    connection(value['BTL_DATABASE_URL'],'btl_app')
    need(len(value['BTL_AUTH_SECRET'])>=64 and 'REPLACE' not in value['BTL_AUTH_SECRET'],'AUTH_SECRET')
    need(all(value[k] for k in required if k.startswith('BTL_SMTP_')),'SMTP_CONFIG')
    need(value['BTL_SANDBOX_V2_RESET_TIMEZONE']=='UTC','RESET_TIMEZONE')
    google=[value.get(k,'') for k in ('BTL_GOOGLE_CLIENT_ID','BTL_GOOGLE_CLIENT_SECRET','BTL_GOOGLE_REDIRECT_URI')]
    if any(google):
        from identity.google import GoogleConfig
        try:GoogleConfig(*google)
        except Exception:raise ConfigurationError('GOOGLE_CONFIG') from None
        need(google[1]!=value['BTL_AUTH_SECRET'],'SEPARATE_GOOGLE_SECRET')
    return dict(value)

def images(value):
    for key,repo,version in (('BTL_PYTHON_IMAGE','python','3.13'),('BTL_NODE_IMAGE','node','22'),('BTL_CADDY_IMAGE','caddy','2'),('BTL_POSTGRES_IMAGE','postgres','17')):
        pattern=r'(?:docker.io/library/)?'+repo+':'+re.escape(version)+r'(?:[.][0-9]+|-[a-z0-9.-]+)*@sha256:[0-9a-f]{64}'
        need(type(value.get(key)) is str and re.fullmatch(pattern,value[key]),'PIN_IMAGE_'+repo.upper())

def site(value):
    domain=value.get('BTL_DOMAIN','')
    need(type(domain) is str and len(domain)<=253 and re.fullmatch(r'(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?[.])+[a-z]{2,63}',domain),'DOMAIN')
    need(type(value.get('BTL_ACME_EMAIL')) is str and re.fullmatch(r'[^\s@]+@[^\s@]+[.][^\s@]+',value['BTL_ACME_EMAIL']),'ACME_EMAIL')
    return domain
