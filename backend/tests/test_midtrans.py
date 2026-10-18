"""Authored offline Midtrans fixtures only; never real funds/provider acceptance."""
import base64
from dataclasses import FrozenInstanceError, replace
import hashlib
import json
import unittest
from unittest.mock import patch

import httpx
from cloud.midtrans import SandboxConfig, SandboxOrder, SnapSandbox, PaymentError, MAX_RESPONSE

KEY = 'SB-Mid-server-authored-fixture-not-real'
ORDER = SandboxOrder('btl-sbx-'+'a'*32, 'qa-account', 'qa-plan-not-for-sale', 10000, 86400)
CONFIG = SandboxConfig(KEY, 'G_QA')


def evidence(**overrides):
    return dict(order_id=ORDER.order_id, merchant_id='G_QA', currency='IDR',
                gross_amount='10000.00', transaction_id='qa-provider-id',
                transaction_status='settlement', fraud_status='accept',
                payment_type='credit_card', status_code='200', **overrides)


def notify(**overrides):
    value = dict(order_id=ORDER.order_id, status_code='200', gross_amount='10000.00',
                 transaction_status='settlement')
    value.update(overrides)
    value['signature_key'] = hashlib.sha512((value['order_id']+value['status_code']+value['gross_amount']+KEY).encode()).hexdigest()
    return value


class MidtransTests(unittest.TestCase):
    def adapter(self, response, *, status=200):
        self.calls = []
        def handler(request):
            self.calls.append(request)
            return httpx.Response(status, json=response) if type(response) is dict else httpx.Response(status, content=response)
        return SnapSandbox(CONFIG, transport=httpx.MockTransport(handler))

    def refuses(self, code, fn, *, uncertain=None):
        with self.assertRaises(PaymentError) as cm: fn()
        self.assertEqual(cm.exception.code, code)
        self.assertNotIn(KEY, str(cm.exception))
        if uncertain is not None: self.assertEqual(cm.exception.uncertain, uncertain)

    def test_fixed_sandbox_card_checkout_and_secret_redaction(self):
        adapter = self.adapter(dict(token='qa-token', redirect_url='https://app.sandbox.midtrans.com/snap/v4/redir/qa-token'))
        result = adapter.checkout(ORDER)
        self.assertEqual((result.mode,result.funds_collected), ('SANDBOX',False))
        self.assertNotIn('qa-token', repr(result)); self.assertNotIn(KEY,repr(CONFIG))
        request, = self.calls
        self.assertEqual(str(request.url),'https://app.sandbox.midtrans.com/snap/v1/transactions')
        self.assertEqual(request.headers['authorization'], 'Basic '+base64.b64encode((KEY+':').encode()).decode())
        body = json.loads(request.content)
        self.assertEqual(body['transaction_details'], dict(order_id=ORDER.order_id,gross_amount=10000))
        self.assertEqual(body['credit_card'],dict(secure=True))
        self.assertEqual(body['enabled_payments'],['credit_card'])
        self.assertNotIn('account_id', body)
        with self.assertRaises(FrozenInstanceError): ORDER.amount_idr = 1

    def test_refuses_production_or_malformed_configuration_and_orders(self):
        for value in ('Mid-server-live', '', KEY+'\n', None):
            self.refuses('SANDBOX_KEY_REQUIRED', lambda: SandboxConfig(value,'G_QA'))
        for field, values in {'order_id':['x','btl-sbx-'+('a'*31),'../x'], 'amount_idr':[True,1.0,0,-1,10**10],
                              'duration_seconds':[True,0,10**10], 'account_id':['','a\n'], 'plan_version':['']}.items():
            for value in values:
                self.refuses('ORDER_INVALID',lambda:replace(ORDER,**{field:value}))

    def test_checkout_redirect_is_never_followed_and_unsafe_urls_refuse(self):
        for url in ('https://evil.test/snap/v4/redir/x', 'http://app.sandbox.midtrans.com/snap/v4/redir/x',
                    'https://app.sandbox.midtrans.com:443/snap/v4/redir/x',
                    'https://app.sandbox.midtrans.com/snap/v4/redir/x?token=secret',
                    'https://app.sandbox.midtrans.com/snap/v4/redir/x#frag',
                    'https://u@app.sandbox.midtrans.com/snap/v4/redir/x', None):
            adapter=self.adapter(dict(token='qa-token',redirect_url=url))
            self.refuses('CHECKOUT_RESPONSE_INVALID',lambda:adapter.checkout(ORDER),uncertain=True)
            self.assertEqual(len(self.calls),1)
        adapter=self.adapter(b'provider body contains secret',status=302)
        self.refuses('PROVIDER_REQUEST_UNCERTAIN',lambda:adapter.checkout(ORDER),uncertain=True)
        self.assertEqual(len(self.calls),1)

    def test_notify_signature_and_unsigned_status_are_signal_only(self):
        adapter=self.adapter(evidence()); value=notify()
        self.assertEqual(adapter.authenticate_notification(json.dumps(value).encode()),ORDER.order_id)
        # Midtrans signature does not cover transaction_status. Never use it as success.
        value['transaction_status']='refund'
        self.assertEqual(adapter.authenticate_notification(json.dumps(value).encode()),ORDER.order_id)
        self.assertEqual(self.calls,[])
        for field in ('gross_amount','order_id','status_code'):
            changed=dict(value);changed[field]=('1' if field=='gross_amount' else 'btl-sbx-'+'b'*32 if field=='order_id' else '201')
            self.refuses('NOTIFICATION_UNAUTHENTICATED',lambda:adapter.authenticate_notification(json.dumps(changed).encode()))
        value['signature_key']='0'*128
        self.refuses('NOTIFICATION_UNAUTHENTICATED',lambda:adapter.authenticate_notification(json.dumps(value).encode()))

    def test_strict_bounded_json_and_duplicate_keys(self):
        adapter=self.adapter(b'{"order_id":"one","order_id":"two"}')
        self.refuses('PROVIDER_JSON_INVALID',lambda:adapter.status(ORDER))
        for raw in (b'[]',b'null',b'{"a":NaN}',b'bad',b'\xff',b'['*2000):
            adapter=self.adapter(raw)
            self.refuses('PROVIDER_JSON_INVALID',lambda:adapter.status(ORDER))
        adapter=self.adapter(b'x'*(MAX_RESPONSE+1))
        self.refuses('PROVIDER_RESPONSE_TOO_LARGE',lambda:adapter.status(ORDER))
        self.refuses('NOTIFICATION_INVALID',lambda:adapter.authenticate_notification(b'x'*(MAX_RESPONSE+1)))

    def test_status_binds_all_server_order_dimensions(self):
        for field,values in {'order_id':['other'], 'merchant_id':['other',None], 'currency':['USD',None],
                             'gross_amount':['1','1e4',10000,10000.0,'10000.01','010000.00',None]}.items():
            for value in values:
                data=evidence();data[field]=value;adapter=self.adapter(data)
                self.refuses('ORDER_EVIDENCE_MISMATCH',lambda:adapter.status(ORDER))
        adapter=self.adapter(evidence())
        self.refuses('TRANSACTION_EVIDENCE_MISMATCH',lambda:adapter.status(ORDER,transaction_id='old-id'))
        adapter=self.adapter(evidence());result=adapter.status(ORDER,transaction_id='qa-provider-id')
        self.assertEqual(result.disposition,'PAID_EVIDENCE')
        self.assertEqual(str(self.calls[0].url),'https://api.sandbox.midtrans.com/v2/'+ORDER.order_id+'/status')
        self.assertFalse(result.funds_collected)
        self.assertFalse(hasattr(result,'tier'))

    def test_states_fraud_reversals_unknowns_fail_closed(self):
        for state,want in [('capture','PAID_EVIDENCE'),('settlement','PAID_EVIDENCE'),('pending','PENDING'),
                           ('refund','REVERSED'),('partial_refund','REVERSED'),('chargeback','REVERSED'),
                           ('partial_chargeback','REVERSED'),('expire','FAILED'),('cancel','FAILED'),
                           ('deny','FAILED'),('failure','FAILED'),('authorize','HOLD'),('new-status','HOLD')]:
            data=evidence();data['transaction_status']=state
            self.assertEqual(self.adapter(data).status(ORDER).disposition,want)
        for state in ('capture','settlement'):
            for fraud in ('challenge','deny',None,'unknown'):
                data=evidence();data.update(transaction_status=state,fraud_status=fraud)
                self.assertEqual(self.adapter(data).status(ORDER).disposition,'HOLD')
        for field,value in [('payment_type','gopay'),('status_code','201')]:
            data=evidence();data[field]=value
            self.assertEqual(self.adapter(data).status(ORDER).disposition,'HOLD')

    def test_timeout_has_no_retry_and_write_uncertainty(self):
        calls=[]
        def handler(request):
            calls.append(request);raise httpx.ReadTimeout('raw secret '+KEY,request=request)
        adapter=SnapSandbox(CONFIG,transport=httpx.MockTransport(handler))
        self.refuses('PROVIDER_REQUEST_UNCERTAIN',lambda:adapter.checkout(ORDER),uncertain=True)
        self.assertEqual(len(calls),1)
        self.refuses('PROVIDER_UNAVAILABLE',lambda:adapter.status(ORDER),uncertain=False)
        self.assertEqual(len(calls),2)

    def test_transport_disables_environment_redirects_and_sets_timeout(self):
        original=httpx.Client
        with patch('cloud.midtrans.httpx.Client',wraps=original) as client:
            self.adapter(evidence()).status(ORDER)
            options=client.call_args.kwargs
        self.assertFalse(options['trust_env']);self.assertFalse(options['follow_redirects'])
        self.assertEqual(options['timeout'].read,10);self.assertEqual(options['timeout'].connect,5)


if __name__ == '__main__': unittest.main()
