import base64,json,uuid
from odoo.tests import tagged
from odoo.tests.common import TransactionCase,new_test_user
from odoo.exceptions import AccessError,UserError

@tagged('post_install','-at_install')
class BusinessTests(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.importer=new_test_user(cls.env,login='btl_import_qa',groups='base.group_user,btl_business.group_import')
        cls.finance=new_test_user(cls.env,login='btl_finance_qa',groups='base.group_user,btl_business.group_finance')
        cls.staff=new_test_user(cls.env,login='btl_staff_qa',groups='base.group_user,btl_business.group_crm')
        cls.portal=new_test_user(cls.env,login='btl_portal_qa',groups='base.group_portal')
    def batch(self):
        actor=str(uuid.uuid4())
        return dict(schemaVersion=1,artifact='BTL-BUSINESS-EXPORT-1',source=str(uuid.uuid4()),mode='SANDBOX',customers=[dict(id=actor,email='authored@example.com')],orders=[dict(id='btl-sbx-'+uuid.uuid4().hex,account=actor,plan='authored-not-for-sale',amountIdr='10000',phase='PAID',revision=1,expiresAt='1792700000')])
    def send(self,value,user=None):
        wizard=self.env['btl.import.batch'].with_user(user or self.importer).create({'file':base64.b64encode(json.dumps(value).encode()),'filename':'authored.json'})
        return wizard.action_import()
    def test_idempotent_projection_never_posts_accounting_or_cash(self):
        value=self.batch();before=self.env['account.move'].search_count([])
        self.send(value);self.send(value)
        rows=self.env['btl.payment'].search([('source','=',value['source'])])
        self.assertEqual(len(rows),1);self.assertEqual(rows.phase,'PAID')
        self.assertEqual(self.env['account.move'].search_count([]),before)
        self.assertEqual(self.env['btl.cash.entry'].search_count([]),0)
        value['orders'][0].update(phase='REVERSED',revision=2);self.send(value)
        value['orders'][0].update(phase='PAID',revision=1);self.send(value)
        self.assertEqual(rows.phase,'REVERSED')
    def test_same_revision_conflict_and_unknown_fields_refuse(self):
        value=self.batch();self.send(value)
        value['orders'][0]['amountIdr']='9999'
        with self.assertRaises(UserError):self.send(value)
        value['password']='never-allowed'
        with self.assertRaises(UserError):self.send(value)
    def test_roles_support_and_portal_isolation(self):
        value=self.batch();self.send(value)
        ticket=self.env['btl.support.ticket'].with_user(self.staff).create({'name':'Authored support question'})
        ticket.write({'state':'working'});self.assertEqual(ticket.state,'working')
        for model in ('btl.customer','btl.payment','btl.cash.entry','btl.support.ticket'):
            with self.assertRaises(AccessError):self.env[model].with_user(self.portal).search_count([])
        with self.assertRaises(AccessError):self.env['btl.payment'].with_user(self.staff).create({})
        with self.assertRaises(AccessError):self.env['btl.cash.entry'].with_user(self.staff).create({'name':'Refused'})
        with self.assertRaises(AccessError):self.env['btl.import.batch'].with_user(self.staff).create({'file':base64.b64encode(b'{}')})
    def test_cashbook_exact_confirmed_totals_and_immutability(self):
        model=self.env['btl.cash.entry'].with_user(self.finance)
        incoming=model.create(dict(name='QA payout',direction='in',category='payout',amount_idr=10000,evidence='QA bank receipt'))
        cost=model.create(dict(name='QA hosting',direction='out',category='vps',amount_idr=3000,evidence='QA cost receipt'))
        self.assertEqual(incoming.signed_idr,0)
        with self.assertRaises(UserError):incoming.with_context(btl_confirming=True).write({'state':'posted'})
        incoming.action_confirm();cost.action_confirm()
        self.assertEqual(incoming.signed_idr+cost.signed_idr,7000)
        with self.assertRaises(UserError):incoming.write({'amount_idr':9000})
        with self.assertRaises(UserError):incoming.unlink()
        with self.assertRaises(UserError):model.create(dict(name='Bypass',direction='in',category='other',amount_idr=1,evidence='QA',state='posted'))
    def test_company_isolation(self):
        other=self.env['res.company'].create({'name':'Other authored QA company'})
        self.env['btl.cash.entry'].create(dict(company_id=other.id,name='Other private cash',direction='in',category='other',amount_idr=1,evidence='Other QA'))
        rows=self.env['btl.cash.entry'].with_user(self.finance).search([('company_id','=',other.id)])
        self.assertFalse(rows)

    def sync_value(self):
        import time
        from datetime import datetime,timezone
        snapshot=self.batch();self.importer.sudo().write({'btl_source':snapshot['source']})
        return dict(schemaVersion=1,artifact='BTL-BUSINESS-SYNC-1',source=snapshot['source'],observedAtUs=str(time.time_ns()//1000),snapshot=snapshot,tickets=[dict(id=str(uuid.uuid4()),account=snapshot['customers'][0]['id'],title='Authored app question',message='Authored support intake',createdAt=datetime.now(timezone.utc).isoformat())])
    def sync(self,value,user=None,company=None):
        return self.env['btl.import.batch'].with_user(user or self.importer).sync_bundle(json.dumps(value),company or self.env.company.id)
    def test_sync_monotonic_company_source_and_staff_status(self):
        value=self.sync_value();self.sync(value);self.sync(value)
        customer=self.env['btl.customer'].search([('source','=',value['source'])]);self.assertIn('PRO',customer.paid_plan)
        tickets=self.env['btl.support.ticket'].search([('source','=',value['source'])]);self.assertEqual(len(tickets),1)
        tickets.with_user(self.staff).write({'state':'working'});self.sync(value);self.assertEqual(tickets.state,'working')
        with self.assertRaises(UserError):tickets.with_user(self.staff).write({'external_id':str(uuid.uuid4())})
        value['observedAtUs']=str(int(value['observedAtUs'])-1)
        with self.assertRaises(UserError):self.sync(value)
        value['source']=str(uuid.uuid4());value['snapshot']['source']=value['source']
        with self.assertRaises(AccessError):self.sync(value)
        with self.assertRaises(AccessError):self.sync(value,company=self.env.company.id+10000)
        with self.assertRaises(AccessError):self.sync(value,user=self.staff)
        with self.assertRaises(AccessError):self.send(value['snapshot'])
    def test_stale_status_is_explicit_unknown(self):
        value=self.sync_value();self.sync(value)
        state=self.env['btl.sync.state'].search([('source','=',value['source'])]);state.observed_us=str(int(state.observed_us)-601000000)
        customer=self.env['btl.customer'].search([('source','=',value['source'])]);self.assertEqual(customer.paid_plan,'STALE / UNKNOWN')
    def test_payout_independent_bank_evidence_and_single_net_cash(self):
        model=self.env['btl.payout.reconciliation'].with_user(self.finance)
        payout=model.create(dict(name='QA-provider-'+uuid.uuid4().hex,bank_reference='QA-bank-'+uuid.uuid4().hex,evidence='Authored QA only',gross_idr=10000,fee_idr=500,refund_idr=1000,bank_idr=8400))
        with self.assertRaises(UserError):payout.action_reconcile()
        self.assertFalse(payout.cash_id);payout.bank_idr=8500;payout.action_reconcile();cash=payout.cash_id;payout.action_reconcile()
        self.assertEqual(payout.cash_id,cash);self.assertEqual(cash.signed_idr,8500)
        with self.assertRaises(UserError):payout.write({'gross_idr':11000})
        with self.assertRaises(AccessError):model.with_user(self.staff).search_count([])
    def test_operating_cost_is_draft_until_actual_receipt(self):
        cost=self.env['btl.operating.cost'].with_user(self.finance).create(dict(name='QA hosting plan',category='vps',expected_idr=3000))
        action=cost.action_prepare();cash=self.env['btl.cash.entry'].with_user(self.finance).browse(action['res_id'])
        self.assertEqual(cash.signed_idr,0)
        with self.assertRaises(UserError):cash.action_confirm()
        cash.write({'evidence':'Authored QA receipt only','amount_idr':3200});cash.action_confirm();self.assertEqual(cash.signed_idr,-3200)
        with self.assertRaises(UserError):cost.action_prepare()
