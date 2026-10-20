"""Offline package constraints, not container runtime acceptance."""
import json,tempfile,unittest,sys,zipfile,hashlib,subprocess
from pathlib import Path
import yaml
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'backend'))
from deploy.vps.settings import runtime,images,site,read_json,ConfigurationError
ROOT=Path(__file__).resolve().parents[3]

def settings():return dict(BTL_DATABASE_URL='host=db dbname=btl user=btl_app password=authored-password',BTL_AUTH_SECRET='a'*64,BTL_SMTP_HOST='smtp.example.com',BTL_SMTP_USER='qa',BTL_SMTP_PASSWORD='qa-not-real',BTL_SMTP_SENDER='qa@example.com',BTL_SANDBOX_V2_RESET_TIMEZONE='UTC')

class PackageTests(unittest.TestCase):
    def test_no_database_api_ports_and_separate_secrets(self):
        data=yaml.safe_load((ROOT/'deploy/vps/compose.yaml').read_text(encoding='utf-8'));services=data['services']
        self.assertNotIn('ports',services['db']);self.assertNotIn('ports',services['api'])
        self.assertEqual(services['api']['network_mode'],'service:gateway');self.assertEqual(services['api']['secrets'],['runtime_config'])
        self.assertEqual(services['operator']['secrets'],['owner_config']);self.assertEqual(services['operator']['profiles'],['ops'])
        self.assertTrue(data['networks']['database']['internal']);self.assertTrue(services['api']['read_only']);self.assertIn('ALL',services['api']['cap_drop'])
        self.assertEqual(services['api']['depends_on']['db']['condition'],'service_healthy')
        caddy=(ROOT/'deploy/vps/Caddyfile').read_text(encoding='utf-8');self.assertIn('admin off',caddy);self.assertIn('127.0.0.1:8001',caddy);self.assertIn('header_up X-Forwarded-For {remote_host}',caddy)
    def test_context_excludes_private_data_and_secrets(self):
        ignore=(ROOT/'.dockerignore').read_text(encoding='utf-8')
        for path in ('frontend/public/market','**/*.csv','**/*.sqlite*','**/.git','**/runtime.json','**/owner.json','**/db_password','backend/tests','**/venv'):self.assertIn(path,ignore)
        docker=(ROOT/'deploy/vps/Dockerfile.api').read_text(encoding='utf-8');self.assertIn('USER 10001:10001',docker);self.assertNotIn('ENV BTL_',docker)
    def test_runtime_roles_secrets_timezone_and_unknown_keys_refuse(self):
        self.assertEqual(runtime(settings()),settings())
        for patch in ({'BTL_DATABASE_URL':'host=db dbname=btl user=btl_owner password=private'},{'BTL_AUTH_SECRET':'short'},{'BTL_SANDBOX_V2_RESET_TIMEZONE':'Asia/Jakarta'},{'BTL_SANDBOX_EVENT_SECRET':'not-for-api'},{'BTL_TRUSTED_PROXY_IPS':'*'},{'BTL_TLS_KEY':'injected'}):
            with self.assertRaises(ConfigurationError):runtime({**settings(),**patch})
    def test_billing_config_requires_full_sandbox_offer_and_separate_worker(self):
        value={**settings(),'BTL_BILLING_DATABASE_URL':'host=db dbname=btl user=btl_billing password=authored-worker',
               'BTL_MIDTRANS_SERVER_KEY':'SB-Mid-server-authored-fixture-not-real','BTL_MIDTRANS_MERCHANT_ID':'G_QA',
               'BTL_BILLING_PLAN_VERSION':'authored-not-for-sale','BTL_BILLING_AMOUNT_IDR':'10000','BTL_BILLING_DURATION_SECONDS':'86400'}
        self.assertEqual(runtime(value),value)
        for patch in ({'BTL_MIDTRANS_SERVER_KEY':'Mid-server-production-refused'},{'BTL_BILLING_DATABASE_URL':settings()['BTL_DATABASE_URL']},{'BTL_BILLING_AMOUNT_IDR':'1.5'},{'BTL_BILLING_DURATION_SECONDS':'0'},{'BTL_MIDTRANS_MERCHANT_ID':''}):
            with self.assertRaises(ConfigurationError):runtime({**value,**patch})
        with self.assertRaises(ConfigurationError):runtime({**settings(),'BTL_BILLING_AMOUNT_IDR':'10000'})

    def test_google_requires_complete_config_and_separate_secret(self):
        with self.assertRaises(ConfigurationError):runtime({**settings(),'BTL_GOOGLE_CLIENT_ID':'1234-authored.apps.googleusercontent.com'})
        value={**settings(),'BTL_GOOGLE_CLIENT_ID':'1234-authored.apps.googleusercontent.com','BTL_GOOGLE_CLIENT_SECRET':'authored-client-secret','BTL_GOOGLE_REDIRECT_URI':'https://app.example.com/api/v1/auth/google/callback'}
        self.assertEqual(runtime(value),value)
        with self.assertRaises(ConfigurationError):runtime({**value,'BTL_GOOGLE_CLIENT_SECRET':'a'*64})
    def test_digest_pins_domain_and_config_redaction(self):
        image={key:repo+':'+version+'@sha256:'+'a'*64 for key,repo,version in (('BTL_PYTHON_IMAGE','python','3.13-slim-bookworm'),('BTL_NODE_IMAGE','node','22-bookworm-slim'),('BTL_CADDY_IMAGE','caddy','2-alpine'),('BTL_POSTGRES_IMAGE','postgres','17-bookworm'))}
        images(image)
        with self.assertRaises(ConfigurationError):images({**image,'BTL_PYTHON_IMAGE':'python:latest'})
        self.assertEqual(site({'BTL_DOMAIN':'app.example.com','BTL_ACME_EMAIL':'ops@example.com'}),'app.example.com')
        for domain in ('*','https://example.com','example.com/path','example.com\ninjected','127.0.0.1'):
            with self.assertRaises(ConfigurationError):site({'BTL_DOMAIN':domain,'BTL_ACME_EMAIL':'ops@example.com'})
        with self.assertRaises(ConfigurationError) as error:runtime({**settings(),'BTL_DATABASE_URL':'host=secret-user:secret-password'})
        self.assertNotIn('secret-password',str(error.exception))
    def test_release_archive_excludes_secrets_market_and_git(self):
        from deploy.vps.package import allowed,archive
        for file in ('frontend/public/market/xauusd-history.json','backend/.env','backend/tests/private.py','backend/venv/password.py','deploy/vps/runtime.json','.git/config','data/raw.csv','../escape.py'):
            self.assertFalse(allowed(file),file)
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'backend'/'cloud'/'app.py';source.parent.mkdir(parents=True);source.write_text('authored QA source',encoding='utf-8')
            hidden=root/'backend'/'.env';hidden.write_text('DO_NOT_SHIP_SECRET',encoding='utf-8');target=root/'candidate.zip'
            manifest=archive(root,['backend/cloud/app.py','backend/.env'],target,'authored-fixture-commit')
            with zipfile.ZipFile(target) as bundle:
                self.assertEqual(set(bundle.namelist()),{'backend/cloud/app.py','RELEASE_MANIFEST.json'})
                self.assertEqual(manifest['files']['backend/cloud/app.py'],hashlib.sha256(source.read_bytes()).hexdigest())
            with self.assertRaises(FileExistsError):archive(root,[],target,'different')
    def test_real_entrypoints_have_no_stdlib_shadowing_and_safe_errors(self):
        for name,args,prefix in [('preflight.py',['--env-file',str(ROOT/'deploy/vps/.env.example')],'PREFLIGHT_REFUSED:PIN_IMAGE_PYTHON'),('runtime.py',['invalid'],'VPS_START_REFUSED:OPERATION'),('ops.py',['invalid'],'VPS_OPERATOR_REFUSED:OPERATION')]:
            result=subprocess.run([sys.executable,'-B',str(ROOT/'deploy/vps'/name),*args],capture_output=True,text=True)
            self.assertEqual(result.returncode,1);self.assertIn(prefix,result.stderr);self.assertNotIn('Traceback',result.stderr)
        result=subprocess.run([sys.executable,'-B',str(ROOT/'deploy/vps/package.py'),'--help'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0)
    def test_valid_preflight_cli_is_explicitly_not_certification(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);owner_password='o'*32
            (root/'runtime.json').write_text(json.dumps(settings()),encoding='utf-8')
            (root/'owner.json').write_text(json.dumps({'BTL_DATABASE_URL':'host=db dbname=btl user=btl_owner password='+owner_password}),encoding='utf-8')
            (root/'db_password').write_text(owner_password,encoding='utf-8')
            data={key:repo+':'+version+'@sha256:'+'a'*64 for key,repo,version in (('BTL_PYTHON_IMAGE','python','3.13-slim-bookworm'),('BTL_NODE_IMAGE','node','22-bookworm-slim'),('BTL_CADDY_IMAGE','caddy','2-alpine'),('BTL_POSTGRES_IMAGE','postgres','17-bookworm'))}
            data.update(BTL_DOMAIN='app.example.com',BTL_ACME_EMAIL='ops@example.com',BTL_SECRET_DIR=root.as_posix())
            config=root/'deploy.env';config.write_text('\n'.join(k+'='+v for k,v in data.items()),encoding='utf-8')
            result=subprocess.run([sys.executable,'-B',str(ROOT/'deploy/vps/preflight.py'),'--env-file',str(config)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr);self.assertIn('NOT_CERTIFIED',result.stdout);self.assertNotIn(owner_password,result.stdout+result.stderr)
    def test_duplicate_json_and_oversized_files_refuse(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'config.json';p.write_text('{"key":"first","key":"second"}',encoding='utf-8')
            with self.assertRaises(ConfigurationError):read_json(p)
            p.write_text(json.dumps({'large':'x'*16385}),encoding='utf-8')
            with self.assertRaises(ConfigurationError):read_json(p)

if __name__=='__main__':unittest.main()
