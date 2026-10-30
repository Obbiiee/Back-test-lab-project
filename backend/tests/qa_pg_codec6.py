"""Checkpoint 6 isolated QA physical codec. Never application configuration."""
import hashlib,json,zlib
from contextlib import contextmanager
from copy import deepcopy
import execution.observed_postgres as storage
from contracts.canonical import canonical_bytes

PREFIX=b'QA6-DAG-ROOT-1\0'
NODE=b'QA6-DAG-ZLIB-1\0'


def wire(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()


def install_schema(dsn):
    with storage.connect(dsn) as db:
        db.execute('CREATE TABLE public.qa6_objects(hash BYTEA PRIMARY KEY CHECK(octet_length(hash)=32),body BYTEA NOT NULL)')
        db.execute('CREATE TABLE public.qa6_format(version TEXT PRIMARY KEY)')
        db.execute("INSERT INTO public.qa6_format VALUES('QA6-DAG-1')")
        db.execute('CREATE TRIGGER qa6_immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON public.qa6_objects FOR EACH STATEMENT EXECUTE FUNCTION btl.deny_evidence_mutation()')


class Codec:
    def __init__(self):self.current=[]

    def pack(self,value):
        original=canonical_bytes(value);normalized=json.loads(original);db,cache=self.current[-1]
        def encode(value,force=False):
            if not isinstance(value,(dict,list)):return value
            node={'d':[[k,encode(v)] for k,v in sorted(value.items())]} if isinstance(value,dict) else {'l':[encode(v) for v in value]}
            if not force and len(wire(value))<256:return node
            raw=wire(node);digest=hashlib.sha256(raw).digest();packed=NODE+zlib.compress(raw,6)
            if digest not in cache:
                inserted=db.execute('INSERT INTO public.qa6_objects VALUES(%s,%s) ON CONFLICT DO NOTHING RETURNING hash',(digest,packed)).fetchone()
                if not inserted:
                    existing=bytes(db.execute('SELECT body FROM public.qa6_objects WHERE hash=%s',(digest,)).fetchone()[0])
                    if existing!=packed:raise ValueError('QA6_OBJECT_IDENTITY_CONFLICT')
                cache[digest]=packed
            return {'r':digest.hex()}
        root=encode(normalized,True)['r']
        return PREFIX+bytes.fromhex(root),hashlib.sha256(original).hexdigest()

    def unpack(self,encoded,expected):
        encoded=bytes(encoded);db,cache=self.current[-1]
        if not encoded.startswith(PREFIX) or len(encoded)!=len(PREFIX)+32:raise ValueError('QA6_ROOT_FORMAT')
        active=set();budget=[0]
        def decode(value,depth=0):
            budget[0]+=1
            if depth>32 or budget[0]>16384:raise ValueError('QA6_LIMIT')
            if not isinstance(value,dict):return value
            if set(value)=={'r'}:
                digest=bytes.fromhex(value['r'])
                if digest in active:raise ValueError('QA6_CYCLE')
                packed=cache.get(digest)
                if packed is None:
                    row=db.execute('SELECT body FROM public.qa6_objects WHERE hash=%s',(digest,)).fetchone()
                    if row is None:raise ValueError('QA6_MISSING_OBJECT')
                    packed=bytes(row[0]);cache[digest]=packed
                if not packed.startswith(NODE):raise ValueError('QA6_OBJECT_FORMAT')
                z=zlib.decompressobj();raw=z.decompress(packed[len(NODE):],1048577)
                if len(raw)>1048576 or not z.eof or z.unused_data or z.unconsumed_tail or hashlib.sha256(raw).digest()!=digest:raise ValueError('QA6_CORRUPT_OBJECT')
                node=json.loads(raw)
                if wire(node)!=raw:raise ValueError('QA6_NONCANONICAL_OBJECT')
                active.add(digest);result=decode(node,depth);active.remove(digest);return result
            if set(value)=={'d'}:
                result={}
                for key,child in value['d']:
                    if key in result:raise ValueError('QA6_DUPLICATE_KEY')
                    result[key]=decode(child,depth+1)
                return result
            if set(value)=={'l'}:return [decode(child,depth+1) for child in value['l']]
            raise ValueError('QA6_INVALID_NODE')
        result=decode({'r':encoded[len(PREFIX):].hex()})
        raw=canonical_bytes(result)
        if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('QA6_LOGICAL_HASH')
        return result

    @contextmanager
    def installed(self):
        native_connect,native_pack,native_unpack=storage.connect,storage.pack,storage.unpack
        @contextmanager
        def connect(dsn):
            with native_connect(dsn) as db:
                self.current.append((db,{}))
                try:yield db
                finally:self.current.pop()
        storage.connect,storage.pack,storage.unpack=connect,self.pack,self.unpack
        try:yield self
        finally:storage.connect,storage.pack,storage.unpack=native_connect,native_pack,native_unpack
