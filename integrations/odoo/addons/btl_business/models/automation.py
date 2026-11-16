import base64,hashlib,json,time
from datetime import datetime,timezone
from dateutil.relativedelta import relativedelta
from odoo import api,fields,models
from odoo.exceptions import AccessError,UserError
from ..contract import sync_decode

class ServiceUser(models.Model):
    _inherit='res.users'
    btl_source=fields.Char(string='Pinned Backtest sync source UUID',groups='base.group_system',copy=False)

class SyncState(models.Model):
    _name='btl.sync.state'
    _description='Latest accepted source observation, not entitlement authority'
    company_id=fields.Many2one('res.company',required=True,index=True)
    source=fields.Char(required=True)
    observed_us=fields.Char(required=True)
    payload_hash=fields.Char(required=True)
    _identity_unique=models.Constraint('UNIQUE(company_id,source)','Source already bound.')

class CustomerStatus(models.Model):
    _inherit='btl.customer'
    paid_plan=fields.Char(compute='_paid_status',string='Billing-only plan projection')
    paid_until=fields.Char(compute='_paid_status',string='Paid expiry UTC')
    sync_observed=fields.Char(compute='_paid_status',string='Source observed UTC')
    def _paid_status(self):
        now=int(time.time())
        for row in self:
            state=self.env['btl.sync.state'].search([('company_id','=',row.company_id.id),('source','=',row.source)],limit=1)
            observed=int(state.observed_us)//1000000 if state else 0
            row.sync_observed=datetime.fromtimestamp(observed,timezone.utc).isoformat() if observed else 'Not synchronized'
            orders=self.env['btl.payment'].search([('customer_id','=',row.id),('phase','=','PAID')])
            expiry=max((int(x.expires_at or 0) for x in orders),default=0)
            row.paid_until=datetime.fromtimestamp(expiry,timezone.utc).isoformat() if 0<expiry<253402300800 else 'Unavailable'
            row.paid_plan='STALE / UNKNOWN' if not 0<=now-observed<=600 else 'PRO (sandbox billing only)' if expiry>now else 'FREE (sandbox billing only)'

class SyncedTicket(models.Model):
    _inherit='btl.support.ticket'
    source=fields.Char(readonly=True,copy=False)
    external_id=fields.Char(readonly=True,copy=False)
    intake_hash=fields.Char(readonly=True,copy=False)
    _identity_unique=models.Constraint('UNIQUE(company_id,source,external_id)','Support intake already synchronized.')
    @api.model_create_multi
    def create(self,vals_list):
        if not self.env.su and any(set(v)&{'source','external_id','intake_hash'} for v in vals_list):raise AccessError('Sync identity is worker-owned.')
        return super().create(vals_list)
    def write(self,vals):
        if any(x.source for x in self) and set(vals)&{'company_id','source','external_id','intake_hash','customer_id'}:raise UserError('Imported ticket identity is immutable.')
        return super().write(vals)

class SyncBatch(models.TransientModel):
    _inherit='btl.import.batch'
    @api.model
    def sync_bundle(self,bundle,company_id):
        if not self.env.user.has_group('btl_business.group_import'):raise AccessError('Importer required.')
        user=self.env.user.sudo()
        if type(company_id) is not int or company_id!=self.env.company.id or user.company_ids.ids!=[company_id] or user.company_id.id!=company_id:raise AccessError('Pinned single company required.')
        if type(bundle) is not str or len(bundle)>8388608:raise UserError('Invalid business bundle.')
        try:value=sync_decode(bundle.encode('utf-8'))
        except (ValueError,TypeError,KeyError,UnicodeError,RecursionError,OverflowError):raise UserError('Invalid business bundle.') from None
        if value['source']!=self.env.user.sudo().btl_source:raise AccessError('Pinned source required.')
        observed=int(value['observedAtUs']);now=time.time_ns()//1000
        if not 0<=now-observed<=600000000:raise UserError('Stale or future source observation.')
        source=value['source'];company=company_id
        key=int.from_bytes(hashlib.sha256(f'{company}:{source}'.encode()).digest()[:8],'big')&0x7fffffffffffffff
        self.env.cr.execute('SELECT pg_advisory_xact_lock(%s)',(key,))
        states=self.env['btl.sync.state'].sudo();state=states.search([('company_id','=',company),('source','=',source)],limit=1)
        sha=hashlib.sha256(bundle.encode()).hexdigest()
        if state and (observed<int(state.observed_us) or observed==int(state.observed_us) and state.payload_hash!=sha):raise UserError('Source observation conflict.')
        self.create({'file':base64.b64encode(json.dumps(value['snapshot']).encode())}).action_import()
        tickets=self.env['btl.support.ticket'].sudo().with_context(tracking_disable=True,mail_create_nosubscribe=True)
        for raw in value['tickets']:
            prior=tickets.search([('company_id','=',company),('source','=',source),('external_id','=',raw['id'])],limit=1)
            digest=hashlib.sha256(json.dumps(raw,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            if prior:
                if prior.intake_hash!=digest:raise UserError('Immutable support intake conflict.')
                continue
            customer=self.env['btl.customer'].sudo().search([('company_id','=',company),('source','=',source),('external_id','=',raw['account'])],limit=1)
            tickets.create(dict(company_id=company,source=source,external_id=raw['id'],intake_hash=digest,customer_id=customer.id,name=raw['title'],description=raw['message'],user_id=False))
        vals=dict(company_id=company,source=source,observed_us=str(observed),payload_hash=sha)
        if state:state.write(vals)
        else:states.create(vals)
        return dict(accepted=True,customers=len(value['snapshot']['customers']),payments=len(value['snapshot']['orders']),tickets=len(value['tickets']))

class Reconciliation(models.Model):
    _name='btl.payout.reconciliation'
    _description='Evidenced provider payout versus bank reconciliation; not sales revenue'
    name=fields.Char(required=True,string='Provider payout reference')
    company_id=fields.Many2one('res.company',required=True,default=lambda self:self.env.company,index=True)
    bank_reference=fields.Char(required=True)
    evidence=fields.Char(required=True)
    date=fields.Date(required=True,default=fields.Date.context_today)
    gross_idr=fields.Integer(required=True)
    fee_idr=fields.Integer(default=0,required=True)
    refund_idr=fields.Integer(default=0,required=True)
    bank_idr=fields.Integer(required=True,string='Observed bank deposit IDR')
    difference_idr=fields.Integer(compute='_difference',store=True)
    state=fields.Selection([('draft','Draft'),('confirmed','Reconciled')],default='draft',required=True)
    cash_id=fields.Many2one('btl.cash.entry',readonly=True,ondelete='restrict')
    _reference_unique=models.Constraint('UNIQUE(company_id,name)','Payout already reconciled.')
    _bank_unique=models.Constraint('UNIQUE(company_id,bank_reference)','Bank deposit already assigned.')
    _amounts=models.Constraint('CHECK(gross_idr BETWEEN 1 AND 1000000000 AND fee_idr BETWEEN 0 AND 1000000000 AND refund_idr BETWEEN 0 AND 1000000000 AND bank_idr BETWEEN 1 AND 1000000000 AND fee_idr+refund_idr<gross_idr)','Invalid positive whole-IDR payout evidence.')
    @api.depends('gross_idr','fee_idr','refund_idr','bank_idr')
    def _difference(self):
        for row in self:row.difference_idr=row.gross_idr-row.fee_idr-row.refund_idr-row.bank_idr
    @api.model_create_multi
    def create(self,vals_list):
        if any(v.get('state','draft')!='draft' or v.get('cash_id') for v in vals_list):raise UserError('Create a draft reconciliation.')
        return super().create(vals_list)
    def _lock_payout(self,operation):
        self.check_access(operation)
        if self:
            self.env.cr.execute('SELECT id FROM btl_payout_reconciliation WHERE id=ANY(%s) ORDER BY id FOR UPDATE',(self.ids,))
            self.invalidate_recordset(['state'])
    def write(self,vals):
        self._lock_payout('write')
        if any(x.state=='confirmed' for x in self) or {'state','cash_id'}&set(vals):raise UserError('Use reconciliation; confirmed evidence is immutable.')
        return super().write(vals)
    def unlink(self):
        self._lock_payout('unlink')
        if any(x.state=='confirmed' for x in self):raise UserError('Confirmed evidence cannot be deleted.')
        return super().unlink()
    def action_reconcile(self):
        self.ensure_one()
        if not self.env.user.has_group('btl_business.group_finance'):raise AccessError('Finance required.')
        self.check_access('write')
        self.env.cr.execute('SELECT id FROM btl_payout_reconciliation WHERE id=%s FOR UPDATE',(self.id,));self.invalidate_recordset()
        if self.state=='confirmed':return True
        if self.difference_idr!=0:raise UserError('Bank deposit does not match gross minus fee and refund.')
        cash=self.env['btl.cash.entry'].create(dict(company_id=self.company_id.id,name='Payout: '+self.name,date=self.date,direction='in',category='payout',amount_idr=self.bank_idr,evidence=self.bank_reference+' / '+self.evidence))
        cash.action_confirm()
        super(Reconciliation,self).write({'state':'confirmed','cash_id':cash.id})
        return True

class OperatingCost(models.Model):
    _name='btl.operating.cost'
    _description='Operating cost plan; drafts require actual receipt confirmation'
    name=fields.Char(required=True)
    company_id=fields.Many2one('res.company',required=True,default=lambda self:self.env.company,index=True)
    vendor_id=fields.Many2one('res.partner',check_company=True)
    category=fields.Selection([(x,x.title()) for x in ('vps','data','software','other')],required=True)
    expected_idr=fields.Integer(required=True)
    period=fields.Selection([('month','Monthly'),('year','Annual')],default='month',required=True)
    next_date=fields.Date(required=True,default=fields.Date.context_today)
    _amount=models.Constraint('CHECK(expected_idr BETWEEN 1 AND 1000000000)','Use positive whole IDR.')
    def action_prepare(self):
        self.ensure_one()
        if not self.env.user.has_group('btl_business.group_finance'):raise AccessError('Finance required.')
        self.check_access('write')
        self.env.cr.execute('SELECT id FROM btl_operating_cost WHERE id=%s FOR UPDATE',(self.id,));self.invalidate_recordset()
        if self.next_date>fields.Date.context_today(self):raise UserError('Next planned cost is not due.')
        cash=self.env['btl.cash.entry'].create(dict(company_id=self.company_id.id,name=self.name+' / '+str(self.next_date),date=self.next_date,direction='out',category=self.category,amount_idr=self.expected_idr,evidence='PLANNED ONLY: replace with actual receipt before confirming'))
        self.next_date=self.next_date+relativedelta(months=1 if self.period=='month' else 12)
        return {'type':'ir.actions.act_window','res_model':'btl.cash.entry','res_id':cash.id,'view_mode':'form','target':'current'}
