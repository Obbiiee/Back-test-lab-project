"""Pure contract and native read-only exporter; no pretend Odoo ORM acceptance."""
from contextlib import contextmanager
import importlib.util,json,os,sys,unittest,uuid
from pathlib import Path
from unittest.mock import patch
import psycopg
from psycopg import sql
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('btl_export',ROOT/'integrations/odoo/export.py');bridge=importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)
from infrastructure.database import migrate,connect
DSN=os.getenv('BTL_TEST_DATABASE_URL')
class OdooContractTests(unittest.TestCase):
    def value(self):
        actor=str(uuid.uuid4());return dict(schemaVersion=1,artifact='BTL-BUSINESS-EXPORT-1',source=str(uuid.uuid4()),mode='SANDBOX',customers=[dict(id=actor,email='authored@example.com')],orders=[dict(id='btl-sbx-'+'a'*32,account=actor,plan='authored',amountIdr='10000',phase='PAID',revision=1,expiresAt='1792700000')])
    def test_exact_business_projection_and_secret_live_shape_refusal(self):
        value=self.value();self.assertEqual(bridge.contract.decode(json.dumps(value).encode()),value)
        for field,data in [('mode','PRODUCTION'),('schemaVersion',True),('password','never-export'),('customers',[]),('source','bad')]:
            with self.assertRaises(ValueError):bridge.contract.decode(json.dumps({**value,field:data}).encode())
        for amount in ('1.5','0','1000000001','1e4'):
            value=self.value();value['orders'][0]['amountIdr']=amount
            with self.assertRaises(ValueError):bridge.contract.decode(json.dumps(value).encode())
        with self.assertRaises(ValueError):bridge.contract.decode(b'{"schemaVersion":1,"schemaVersion":1}')
        with self.assertRaises(ValueError):bridge.contract.decode(b'x'*(bridge.contract.MAX_BYTES+1))

@unittest.skipUnless(DSN,'Requires isolated QA PostgreSQL; skip is not acceptance')
class OdooExportTests(unittest.TestCase):
    def test_real_reader_role_has_no_password_tick_or_write_access(self):
        migrate(DSN);actor=str(uuid.uuid4());role='business_export_'+uuid.uuid4().hex
        with connect(DSN) as db:db.execute("INSERT INTO btl.users(id,email,hashed_password) VALUES (%s,%s,'never-export-password')",(actor,actor+'@example.com'))
        with psycopg.connect(DSN,autocommit=True) as db:db.execute(sql.SQL('CREATE ROLE {} NOLOGIN').format(sql.Identifier(role)))
        bridge.grant_export_reader(DSN,role)
        @contextmanager
        def limited(dsn):
            with connect(dsn) as db:db.execute(sql.SQL('SET LOCAL ROLE {}').format(sql.Identifier(role)));yield db
        with patch.object(bridge,'connect',limited):raw=bridge.snapshot(DSN,str(uuid.uuid4()))
        value=bridge.contract.decode(raw);self.assertIn(actor,[c['id'] for c in value['customers']]);self.assertNotIn(b'never-export-password',raw)
        for statement in ('SELECT hashed_password FROM btl.users','SELECT * FROM btl.tick_sessions LIMIT 0','UPDATE btl.users SET email=email','SELECT transaction_id FROM btl.sandbox_billing_orders'):
            with self.assertRaises(psycopg.DatabaseError):
                with limited(DSN) as db:db.execute(statement)
class OdooPackageTests(unittest.TestCase):
    def test_archive_admits_only_source_not_customer_exports_or_secrets(self):
        sys.path.insert(0,str(ROOT))
        from deploy.vps.package import allowed
        for path in ('integrations/odoo/export.py','integrations/odoo/addons/btl_business/security/ir.model.access.csv','integrations/odoo/LICENSE','integrations/odoo/compose.yaml'):
            self.assertTrue(allowed(path))
        for path in ('integrations/odoo/customers.json','integrations/odoo/orders.csv','integrations/odoo/secrets/private.py','integrations/odoo/tests/private.py'):
            self.assertFalse(allowed(path))

if __name__=='__main__':unittest.main()
