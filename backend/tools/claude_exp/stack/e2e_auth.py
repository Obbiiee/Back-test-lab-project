import json, urllib.request, urllib.parse, urllib.error, time, pathlib, uuid
B="http://127.0.0.1:8001"; OUT=pathlib.Path.home()/".riksora_local_stack/outbox.jsonl"
H={"X-Forwarded-Proto":"https","X-Forwarded-For":"127.0.0.1"}
def call(m,p,body=None,form=None,tok=None):
    h=dict(H); data=None
    if body is not None: data=json.dumps(body).encode(); h["Content-Type"]="application/json"
    if form is not None: data=urllib.parse.urlencode(form).encode(); h["Content-Type"]="application/x-www-form-urlencoded"
    if tok: h["Authorization"]="Bearer "+tok
    try:
        r=urllib.request.urlopen(urllib.request.Request(B+p,data,h,method=m),timeout=30); return r.status,r.read()
    except urllib.error.HTTPError as e: return e.code,e.read()
def tokfor(email):
    for _ in range(20):
        if OUT.exists():
            for l in reversed(OUT.read_text().splitlines()):
                d=json.loads(l)
                if d["email"]==email and d["purpose"]=="verification": return d["token"]
        time.sleep(.3)
PW="Test fixture passphrase 2026 only"
users=[]
for n in "ab":
    e=f"user{n}-{uuid.uuid4().hex[:6]}@example.com"
    s,b=call("POST","/api/v1/auth/register",{"email":e,"password":PW}); print("register",n,s)
    s,b=call("POST","/api/v1/auth/login",form={"username":e,"password":PW}); print("login before verify (expect 400)",s)
    s,b=call("POST","/api/v1/auth/verify",{"token":tokfor(e)}); print("verify",s)
    s,b=call("POST","/api/v1/auth/login",form={"username":e,"password":PW}); print("login",s)
    users.append((e,json.loads(b)["access_token"]))
for e,t in users:
    s,b=call("GET","/api/v1/auth/me",tok=t); print("me",s,json.loads(b).get("email")==e)
s,b=call("GET","/api/v1/auth/me"); print("me no token (expect 401)",s)
s,b=call("GET","/api/v1/workspaces",tok=users[0][1]); print("ws list A",s,b[:200])
s,b=call("POST","/api/v1/workspaces",{"name":"A-private"},tok=users[0][1]); print("create ws A",s,b[:300])
s,b=call("GET","/api/v1/workspaces",tok=users[1][1]); print("ws list B",s,b[:200])
wid=json.loads(call("POST","/api/v1/workspaces",{"name":"A2"},tok=users[0][1])[1])["id"]
for who,(e,t) in zip("AB",users):
    for p in (f"/api/v1/workspaces/{wid}",f"/api/v1/workspaces/{wid}/sessions"):
        print("cross",who,p.split(wid)[1] or "/",call("GET",p,tok=t)[0])
