"""Private Node adapter -> actual HTTPS ASGI -> isolated PostgreSQL QA bridge.
Not a browser, network TLS certificate, real Google or merchant acceptance.
"""
import os,json,secrets,uuid,subprocess,threading,tempfile,unittest
from pathlib import Path
from cloud.app import create_app
from infrastructure.database import migrate
from tests.test_identity import client,RecordingDelivery,PASSWORD
from tests.test_research_sessions import method
from tests.test_kernel_v2 import opening
from execution.research_fixture_v2 import START_NS,STEP_NS

class BetaClientNativeTests(unittest.TestCase):
    def test_actual_node_adapter_commits_exact_v2_receipts(self):
        dsn=os.environ.get('BTL_TEST_DATABASE_URL')
        self.assertTrue(dsn,'Fresh isolated QA DSN required; missing is not PASS')
        migrate(dsn);delivery=RecordingDelivery()
        app=create_app(dsn,secrets.token_urlsafe(48),delivery,rate_limit=1000,sandbox_reset_timezone='UTC')
        http=client(app);email=uuid.uuid4().hex+'@example.com'
        self.assertEqual(http.post('/api/v1/auth/register',json=dict(email=email,password=PASSWORD)).status_code,201)
        self.assertEqual(http.post('/api/v1/auth/verify',json=dict(token=delivery.token(email,'verification'))).status_code,200)
        login=http.post('/api/v1/auth/login',data=dict(username=email,password=PASSWORD)).json()
        ws=http.post('/api/v1/workspaces',headers={'Authorization':'Bearer '+login['access_token']},json=dict(name='Node adapter isolated QA'))
        self.assertEqual(ws.status_code,201)
        config=dict(email=email,password=PASSWORD,workspace=ws.json()['id'],method=method(),opening=opening(entry='999',sl='1.09902'),start=str(START_NS),next=str(START_NS+STEP_NS),last=str(START_NS+2*STEP_NS))
        driver=Path(__file__).with_name('beta-client-native.mjs')
        with tempfile.TemporaryFile(mode='w+t',encoding='utf-8') as errors:
            process=subprocess.Popen(['node',str(driver)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=errors,text=True,encoding='utf-8',env={k:v for k,v in os.environ.items() if k!='BTL_TEST_DATABASE_URL'})
            deadline=threading.Timer(90,process.kill);deadline.start()
            complete=False
            try:
                process.stdin.write(json.dumps(config)+'\n');process.stdin.flush()
                for line in process.stdout:
                    item=json.loads(line)
                    if item.get('complete') is True:complete=True;break
                    path=item['path'];options=item['options']
                    self.assertTrue(path.startswith('/api/v1/') and '?' not in path)
                    response=http.request(options['method'],path,headers=options['headers'],content=options.get('body'))
                    # Private pipe contains ephemeral QA bearer only, never output/logs.
                    process.stdin.write(json.dumps(dict(status=response.status_code,body=response.text))+'\n');process.stdin.flush()
                process.stdin.close();code=process.wait(timeout=10)
                if code!=0:
                    errors.seek(0);self.fail('Node adapter QA failed: '+errors.read()[-4000:])
                self.assertTrue(complete,'Node adapter did not finish')
            finally:
                deadline.cancel()
                if process.poll() is None:process.kill();process.wait()
                process.stdout.close()

if __name__=='__main__':unittest.main(verbosity=2)
