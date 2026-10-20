from odoo import api,fields,models
from odoo.exceptions import AccessError,UserError

class Customer(models.Model):
    _name='btl.customer'
    _description='Backtest Lab customer projection'
    _rec_name='email'
    company_id=fields.Many2one('res.company',required=True,default=lambda self:self.env.company,index=True)
    source=fields.Char(required=True,readonly=True)
    external_id=fields.Char(required=True,readonly=True)
    email=fields.Char(required=True,readonly=True)
    partner_id=fields.Many2one('res.partner',required=True,ondelete='restrict',check_company=True)
    _identity_unique=models.Constraint('UNIQUE(company_id,source,external_id)','Customer identity already imported.')

class Payment(models.Model):
    _name='btl.payment'
    _description='Sandbox payment projection - not accounting revenue'
    _rec_name='external_id'
    company_id=fields.Many2one('res.company',required=True,default=lambda self:self.env.company,index=True)
    source=fields.Char(required=True,readonly=True)
    external_id=fields.Char(required=True,readonly=True)
    customer_id=fields.Many2one('btl.customer',required=True,ondelete='restrict',check_company=True)
    plan=fields.Char(required=True,readonly=True)
    amount_idr=fields.Integer(required=True,readonly=True,string='Order face value IDR (simulated)')
    phase=fields.Selection([(x,x) for x in ('CREATED','CHECKOUT_STARTED','PENDING','FAILED','PAID','REVERSED','HOLD')],required=True,readonly=True)
    revision=fields.Integer(required=True,readonly=True)
    expires_at=fields.Char(readonly=True)
    payload_hash=fields.Char(required=True,readonly=True)
    mode=fields.Selection([('SANDBOX','Sandbox - no real funds')],default='SANDBOX',required=True,readonly=True)
    _identity_unique=models.Constraint('UNIQUE(company_id,source,external_id)','Payment identity already imported.')
    _amount_check=models.Constraint('CHECK(amount_idr>0 AND amount_idr<=1000000000 AND revision>=0)','Invalid exact IDR amount or revision.')

class Ticket(models.Model):
    _name='btl.support.ticket'
    _description='Backtest Lab support ticket'
    _inherit=['mail.thread','mail.activity.mixin']
    name=fields.Char(required=True,tracking=True)
    company_id=fields.Many2one('res.company',required=True,default=lambda self:self.env.company,index=True)
    customer_id=fields.Many2one('btl.customer',check_company=True,ondelete='restrict')
    user_id=fields.Many2one('res.users',default=lambda self:self.env.user)
    state=fields.Selection([('open','Open'),('working','In progress'),('closed','Closed')],default='open',required=True,tracking=True)
    description=fields.Text()

class CashEntry(models.Model):
    _name='btl.cash.entry'
    _description='Manually evidenced IDR cashbook - not payment settlement authority'
    _inherit=['mail.thread']
    name=fields.Char(required=True)
    company_id=fields.Many2one('res.company',required=True,default=lambda self:self.env.company,index=True)
    date=fields.Date(required=True,default=fields.Date.context_today)
    direction=fields.Selection([('in','Cash in'),('out','Cash out')],required=True)
    category=fields.Selection([(x,x.title()) for x in ('opening','payout','refund','fee','vps','data','software','other')],required=True)
    amount_idr=fields.Integer(required=True,string='Amount IDR')
    signed_idr=fields.Integer(compute='_signed',store=True,string='Net cash IDR')
    evidence=fields.Char(required=True,help='Bank/receipt reference. Never enter passwords or card details.')
    state=fields.Selection([('draft','Draft'),('posted','Confirmed')],default='draft',required=True,tracking=True)
    _amount_check=models.Constraint('CHECK(amount_idr>0 AND amount_idr<=1000000000)','Use a positive whole-IDR amount up to one billion per entry.')
    @api.depends('amount_idr','direction','state')
    def _signed(self):
        for row in self:row.signed_idr=0 if row.state!='posted' else row.amount_idr*(1 if row.direction=='in' else -1)
    @api.model_create_multi
    def create(self,vals_list):
        if any(vals.get('state','draft')!='draft' for vals in vals_list):raise UserError('Create a draft first.')
        return super().create(vals_list)
    def _lock_cash(self,operation):
        self.check_access(operation)
        if self:
            self.env.cr.execute('SELECT id FROM btl_cash_entry WHERE id=ANY(%s) ORDER BY id FOR UPDATE',(self.ids,))
            self.invalidate_recordset(['state'])
    def write(self,vals):
        self._lock_cash('write')
        if any(row.state=='posted' for row in self):raise UserError('Confirmed cash entries are immutable; add a correcting entry.')
        if 'state' in vals:raise UserError('Use Confirm.')
        return super().write(vals)
    def unlink(self):
        self._lock_cash('unlink')
        if any(row.state=='posted' for row in self):raise UserError('Confirmed cash entries cannot be deleted.')
        return super().unlink()
    def action_confirm(self):
        if not self.env.user.has_group('btl_business.group_finance'):raise AccessError('Finance role required.')
        self._lock_cash('write')
        drafts=self.filtered(lambda row:row.state=='draft')
        if any(row.evidence.startswith('PLANNED ONLY:') or not row.evidence.strip() for row in drafts):raise UserError('Actual bank or receipt evidence required.')
        return super(CashEntry,drafts).write({'state':'posted'}) if drafts else True
