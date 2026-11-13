import sys;sys.path.insert(0,'tools/claude_exp')
from common import *
import tempfile
rows=read_real_rows(500);w=tempfile.mkdtemp()
p,res,_=ingest_engine(rows,w)
d=p.describe_v2(p.dataset_id,p.dataset_version)
print(list(d.keys())); print({k:d[k] for k in d if k!='root'} if len(str(d))<1500 else list(d['root'].keys()))
print({k:(v if k not in('root',) else '..') for k,v in res.items()})
