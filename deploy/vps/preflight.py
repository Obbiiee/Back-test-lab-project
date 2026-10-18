"""Offline settings validation only; no Docker/database/provider certification."""
import argparse,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'backend'))
from deploy.vps.settings import read_json,runtime,images,site,connection,need,ConfigurationError

def main():
    from dotenv import dotenv_values
    parser=argparse.ArgumentParser();parser.add_argument('--env-file',required=True);args=parser.parse_args()
    value=dotenv_values(args.env_file);images(value);domain=site(value)
    folder=Path(value.get('BTL_SECRET_DIR',''));need(folder.is_absolute() and folder.is_dir(),'SECRET_DIRECTORY')
    settings=runtime(read_json(folder/'runtime.json'))
    owner=read_json(folder/'owner.json');need(set(owner)=={'BTL_DATABASE_URL'},'OWNER_CONFIG_KEYS');connection(owner['BTL_DATABASE_URL'],'btl_owner')
    from psycopg.conninfo import conninfo_to_dict
    password=(folder/'db_password').read_text(encoding='utf-8').rstrip('\r\n');need(len(password)>=32,'DATABASE_OWNER_PASSWORD')
    owner_fields=conninfo_to_dict(owner['BTL_DATABASE_URL']);runtime_fields=conninfo_to_dict(settings['BTL_DATABASE_URL'])
    need(owner_fields['password']==password,'DATABASE_OWNER_PASSWORD_MATCH')
    need(runtime_fields['password']!=password,'SEPARATE_DATABASE_PASSWORDS')
    if settings.get('BTL_GOOGLE_REDIRECT_URI'):
        need(settings['BTL_GOOGLE_REDIRECT_URI']=='https://'+domain+'/api/v1/auth/google/callback','GOOGLE_REDIRECT_ORIGIN')
    print('CONFIGURATION_VALIDATED_ONLY; Docker/Linux/TLS/SMTP/Google/merchant/rights/capacity/UI/release acceptance NOT_CERTIFIED')

if __name__=='__main__':
    try:main()
    except Exception as error:print('PREFLIGHT_REFUSED:'+(str(error) if isinstance(error,ConfigurationError) else type(error).__name__),file=sys.stderr);raise SystemExit(1) from None
