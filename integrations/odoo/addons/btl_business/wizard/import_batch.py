import base64,hashlib
from odoo import fields,models
from odoo.exceptions import AccessError,UserError
from ..contract import decode,digest

class ImportBatch(models.TransientModel):
    _name='btl.import.batch'
    _description='Import reviewed sandbox projection'
    file=fields.Binary(required=True)
    filename=fields.Char()
    def action_import(self):
        self.ensure_one()
        if not self.env.user.has_group('btl_business.group_import'):raise AccessError('Business importer role required.')
        try:
            if len(self.file)>2800000:raise ValueError()
            value=decode(base64.b64decode(self.file,validate=True))
        except (ValueError,TypeError,KeyError,UnicodeError,RecursionError):raise UserError('Invalid or oversized sandbox projection.') from None
        company=self.env.company.id;source=value['source']
        key=int.from_bytes(hashlib.sha256(f'{company}:{source}'.encode()).digest()[:8],'big')&0x7fffffffffffffff
        self.env.cr.execute('SELECT pg_advisory_xact_lock(%s)',(key,))
        env=self.env(context=dict(self.env.context,tracking_disable=True,mail_create_nosubscribe=True))
        customers=env['btl.customer'].sudo();payments=env['btl.payment'].sudo();mapping={}
        for raw in value['customers']:
            domain=[('company_id','=',company),('source','=',source),('external_id','=',raw['id'])]
            customer=customers.search(domain,limit=1)
            if customer and customer.email!=raw['email']:raise UserError('Customer email changed; review source identity before importing.')
            if not customer:
                partner=env['res.partner'].sudo().create(dict(name=raw['email'],email=raw['email'],company_id=company))
                customer=customers.create(dict(company_id=company,source=source,external_id=raw['id'],email=raw['email'],partner_id=partner.id))
            mapping[raw['id']]=customer
        for raw in value['orders']:
            row=payments.search([('company_id','=',company),('source','=',source),('external_id','=',raw['id'])],limit=1)
            sha=digest(raw)
            if row:
                if (row.customer_id.id,row.plan,row.amount_idr)!=(mapping[raw['account']].id,raw['plan'],int(raw['amountIdr'])):raise UserError('Immutable payment identity conflict.')
                if raw['revision']<row.revision:continue
                if raw['revision']==row.revision:
                    if row.payload_hash!=sha:raise UserError('Same-revision payment conflict.')
                    continue
                if row.phase=='REVERSED' and raw['phase']!='REVERSED':raise UserError('Reversal is terminal.')
            vals=dict(company_id=company,source=source,external_id=raw['id'],customer_id=mapping[raw['account']].id,plan=raw['plan'],amount_idr=int(raw['amountIdr']),phase=raw['phase'],revision=raw['revision'],expires_at=raw['expiresAt'] or False,payload_hash=sha,mode='SANDBOX')
            if row:row.write(vals)
            else:payments.create(vals)
        return {'type':'ir.actions.act_window_close'}
