"""Independent Python/pandas reference for Issue #21 C-06 indicators.

Written from the formula definitions (not translated from the JS code) and
using pandas rolling windows where possible, so it is a second code path.
Run:  python3 tests/fixtures/c06_reference.py > tests/fixtures/c06-golden.json
The JS test compares every output point to these values (tolerance 1e-8).
"""
import json, math
import numpy as np
import pandas as pd

def fixture():
    # Deterministic 1h bars over 14 UTC days, with flat candles and a gap-free walk.
    seed = 20261103
    def rnd():
        nonlocal seed
        seed = (seed * 48271) % 2147483647
        return seed / 2147483647
    rows, price, t0 = [], 2650.0, 1736121600  # 2025-01-06 00:00 UTC
    for i in range(336):
        drift = math.sin(i / 17) * 2.2 + math.cos(i / 41) * 1.4 + (rnd() - .5) * 4
        o = price; c = max(1.0, o + drift)
        if i % 47 == 0: c = o  # flat close
        h = max(o, c) + (0 if i % 53 == 0 else rnd() * 3)
        l = min(o, c) - (0 if i % 53 == 0 else rnd() * 3)
        if i % 53 == 0: h = l = o = c  # fully flat candle
        rows.append(dict(time=t0 + i * 3600, open=round(o, 3), high=round(h, 3), low=round(l, 3), close=round(c, 3)))
        price = c
    return rows

bars = fixture()
df = pd.DataFrame(bars)
O, H, L, C = df.open, df.high, df.low, df.close
HL2 = (H + L) / 2
HLC3 = (H + L + C) / 3
N = len(df)

def sma(s, n): return s.rolling(n, min_periods=n).mean()
def ema(s, n):
    # SMA seed over the first n valid values, then alpha = 2/(n+1).
    v = s.to_numpy(dtype=float); out = np.full(len(v), np.nan)
    idx = np.where(~np.isnan(v))[0]
    if len(idx) < n: return pd.Series(out)
    start = idx[0]; out[start + n - 1] = v[start:start + n].mean(); a = 2 / (n + 1)
    for i in range(start + n, len(v)): out[i] = a * v[i] + (1 - a) * out[i - 1]
    return pd.Series(out)
def rma(s, n):
    v = s.to_numpy(dtype=float); out = np.full(len(v), np.nan)
    idx = np.where(~np.isnan(v))[0]
    if len(idx) < n: return pd.Series(out)
    start = idx[0]; out[start + n - 1] = v[start:start + n].mean()
    for i in range(start + n, len(v)): out[i] = (out[i - 1] * (n - 1) + v[i]) / n
    return pd.Series(out)
def wma(s, n):
    w = np.arange(1, n + 1, dtype=float)
    return s.rolling(n, min_periods=n).apply(lambda x: float(np.dot(x, w) / w.sum()), raw=True)
def tr():
    pc = C.shift(1)
    t = pd.concat([H - L, (H - pc).abs(), (L - pc).abs()], axis=1).max(axis=1)
    t.iloc[0] = H.iloc[0] - L.iloc[0]
    return t
def atr(n): return rma(tr(), n)
def std_pop(s, n): return s.rolling(n, min_periods=n).std(ddof=0)
def linreg_end(s, n):
    x = np.arange(n, dtype=float)
    def f(y):
        slope, intercept = np.polyfit(x, y, 1)
        return intercept + slope * (n - 1)
    return s.rolling(n, min_periods=n).apply(f, raw=True)
def hh(s, n): return s.rolling(n, min_periods=n).max()
def ll(s, n): return s.rolling(n, min_periods=n).min()

def pts(series):
    return [[int(df.time[i]), float(v)] for i, v in enumerate(series) if v is not None and not (isinstance(v, float) and math.isnan(v)) and not pd.isna(v)]

G = {}
G['WMA'] = pts(wma(C, 20))
G['RMA'] = pts(rma(C, 14))
G['HMA'] = pts(wma(2 * wma(C, 10) - wma(C, 20), round(math.sqrt(20))))
e1 = ema(C, 20); e2 = ema(e1, 20); e3 = ema(e2, 20)
G['DEMA'] = pts(2 * e1 - e2)
G['TEMA'] = pts(3 * e1 - 3 * e2 + e3)
lag = (20 - 1) // 2
G['ZLEMA'] = pts(ema(2 * C - C.shift(lag), 20))
# KAMA(10,2,30): seed close[9]
k = np.full(N, np.nan); k[9] = C[9]; fs, ss = 2 / 3, 2 / 31
change = (C - C.shift(10)).abs(); vol = C.diff().abs().rolling(10).sum()
for i in range(10, N):
    er = 0 if vol[i] == 0 else change[i] / vol[i]
    sc = (er * (fs - ss) + ss) ** 2
    k[i] = k[i - 1] + sc * (C[i] - k[i - 1])
G['KAMA'] = pts(pd.Series(k))
G['LINREG'] = pts(linreg_end(C, 20))
G['STDDEV'] = pts(std_pop(C, 20))
G['MA_RIBBON'] = {f'ma{i+1}': pts(ema(C, p)) for i, p in enumerate([20, 30, 40, 50])}
G['MA_RIBBON'].update({'ma5': [], 'ma6': []})
G['NATR'] = pts(100 * atr(14) / C)

# Supertrend(10, 3)
a = atr(10); up_b = HL2 + 3 * a; lo_b = HL2 - 3 * a
fu = np.full(N, np.nan); fl = np.full(N, np.nan); st = []
uptrend = False
for i in range(N):
    if pd.isna(a[i]): continue
    first = i == 0 or np.isnan(fu[i - 1])
    if first:
        fu[i], fl[i] = up_b[i], lo_b[i]; uptrend = False
    else:
        fu[i] = up_b[i] if (up_b[i] < fu[i - 1] or C[i - 1] > fu[i - 1]) else fu[i - 1]
        fl[i] = lo_b[i] if (lo_b[i] > fl[i - 1] or C[i - 1] < fl[i - 1]) else fl[i - 1]
        uptrend = (C[i] >= fl[i]) if uptrend else (C[i] > fu[i])
    st.append([int(df.time[i]), float(fl[i] if uptrend else fu[i])])
G['SUPERTREND'] = {'trend': st}

mid = lambda n: (hh(H, n) + ll(L, n)) / 2
ten, kij, sb = mid(9), mid(26), mid(52)
G['ICHIMOKU'] = {'conversion': pts(ten), 'base': pts(kij), 'spanA': pts(((ten + kij) / 2).shift(26)), 'spanB': pts(sb.shift(26)), 'lagging': pts(C.shift(-26))}
km = ema(C, 20); ka = atr(10)
G['KELTNER'] = {'middle': pts(km), 'upper': pts(km + 2 * ka), 'lower': pts(km - 2 * ka)}
du, dl = hh(H, 20), ll(L, 20)
G['DONCHIAN'] = {'upper': pts(du), 'lower': pts(dl), 'basis': pts((du + dl) / 2)}
# Regression channel: fit ± 2 · residual population std
mid_c, up_c, lo_c = [], [], []
x = np.arange(20, dtype=float)
for i in range(19, N):
    y = C[i - 19:i + 1].to_numpy(); slope, icp = np.polyfit(x, y, 1)
    fit = icp + slope * x; sd = math.sqrt(((y - fit) ** 2).mean()); v = icp + slope * 19
    t = int(df.time[i]); mid_c.append([t, v]); up_c.append([t, v + 2 * sd]); lo_c.append([t, v - 2 * sd])
G['LINREG_CHANNEL'] = {'basis': mid_c, 'upper': up_c, 'lower': lo_c}

# Parabolic SAR (.02, .02, .2)
def psar(start=.02, inc=.02, mx=.2):
    longp = C[1] >= C[0]; af = start
    ep = max(H[0], H[1]) if longp else min(L[0], L[1]); sar = min(L[0], L[1]) if longp else max(H[0], H[1])
    out = [[int(df.time[1]), float(sar)]]
    for i in range(2, N):
        nxt = sar + af * (ep - sar)
        if longp:
            nxt = min(nxt, L[i - 1], L[i - 2])
            if L[i] < nxt: longp, nxt, ep, af = False, ep, L[i], start
            elif H[i] > ep: ep, af = H[i], min(mx, af + inc)
        else:
            nxt = max(nxt, H[i - 1], H[i - 2])
            if H[i] > nxt: longp, nxt, ep, af = True, ep, H[i], start
            elif L[i] < ep: ep, af = L[i], min(mx, af + inc)
        sar = nxt; out.append([int(df.time[i]), float(sar)])
    return out
G['PSAR'] = psar()
G['ALLIGATOR'] = {'jaw': pts(rma(HL2, 13).shift(8)), 'teeth': pts(rma(HL2, 8).shift(5)), 'lips': pts(rma(HL2, 5).shift(3))}

# Daily pivots (classic) from the prior completed UTC day
day = df.time // 86400
daily = df.groupby(day).agg(high=('high', 'max'), low=('low', 'min'), close=('close', 'last'))
piv = {k: [] for k in ['p', 'r1', 'r2', 'r3', 's1', 's2', 's3']}
adr = []
days_sorted = list(daily.index)
for i in range(N):
    d = day[i]; pos = days_sorted.index(d)
    if pos >= 1:
        h, l, c = daily.loc[days_sorted[pos - 1]]
        p = (h + l + c) / 3
        lv = dict(p=p, r1=2 * p - l, r2=p + (h - l), r3=h + 2 * (p - l), s1=2 * p - h, s2=p - (h - l), s3=l - 2 * (h - p))
        for kk, vv in lv.items(): piv[kk].append([int(df.time[i]), float(vv)])
    if pos >= 14:
        rng = [(daily.loc[days_sorted[j]].high - daily.loc[days_sorted[j]].low) for j in range(pos - 14, pos)]
        adr.append([int(df.time[i]), float(sum(rng) / 14)])
G['PIVOTS'] = piv
G['ADR'] = adr

# Fractals 2/2 (strict)
fu_, fd_ = [], []
for i in range(2, N - 2):
    others = [j for j in range(i - 2, i + 3) if j != i]
    if all(H[j] < H[i] for j in others): fu_.append([int(df.time[i]), float(H[i])])
    if all(L[j] > L[i] for j in others): fd_.append([int(df.time[i]), float(L[i])])
G['FRACTALS'] = {'up': fu_, 'down': fd_}

# RSI (Wilder) and Stoch RSI (14,14,3,3)
def rsi(s, n):
    d = s.diff(); g = d.clip(lower=0); lo = (-d).clip(lower=0)
    ag = np.full(N, np.nan); al = np.full(N, np.nan); out = np.full(N, np.nan)
    ag[n] = g[1:n + 1].mean(); al[n] = lo[1:n + 1].mean()
    for i in range(n + 1, N): ag[i] = (ag[i - 1] * (n - 1) + g[i]) / n; al[i] = (al[i - 1] * (n - 1) + lo[i]) / n
    for i in range(n, N): out[i] = 50 if al[i] == 0 and ag[i] == 0 else 100 if al[i] == 0 else 100 - 100 / (1 + ag[i] / al[i])
    return pd.Series(out)
r = rsi(C, 14); rh, rl = r.rolling(14, min_periods=14).max(), r.rolling(14, min_periods=14).min()
raw = np.where(rh == rl, 50, 100 * (r - rl) / (rh - rl)); raw = pd.Series(raw).where(~rh.isna())
sk = sma(raw, 3)
G['STOCH_RSI'] = {'k': pts(sk), 'd': pts(sma(sk, 3))}

# Wilder DMI / ADX(14)
up = H.diff(); dn = -L.diff()
pdm = np.where((up > dn) & (up > 0), up, 0.0); mdm = np.where((dn > up) & (dn > 0), dn, 0.0)
t = tr().to_numpy(); n = 14
sT = sP = sM = 0.0; plus = np.full(N, np.nan); minus = np.full(N, np.nan); dx = np.full(N, np.nan)
for i in range(1, N):
    if i <= n:
        sT += t[i]; sP += pdm[i]; sM += mdm[i]
        if i < n: continue
    else:
        sT = sT - sT / n + t[i]; sP = sP - sP / n + pdm[i]; sM = sM - sM / n + mdm[i]
    plus[i] = 0 if sT == 0 else 100 * sP / sT; minus[i] = 0 if sT == 0 else 100 * sM / sT
    ssum = plus[i] + minus[i]; dx[i] = 0 if ssum == 0 else 100 * abs(plus[i] - minus[i]) / ssum
G['ADX'] = pts(rma(pd.Series(dx), 14))
G['DMI'] = {'plus': pts(pd.Series(plus)), 'minus': pts(pd.Series(minus))}

tpm = sma(HLC3, 20); md = HLC3.rolling(20).apply(lambda w: np.abs(w - w.mean()).mean(), raw=True)
G['CCI'] = pts(np.where(md == 0, 0, (HLC3 - tpm) / (0.015 * md)) * np.where(tpm.isna(), np.nan, 1))
G['ROC'] = pts(100 * (C - C.shift(12)) / C.shift(12))
G['MOMENTUM'] = pts(C - C.shift(10))
h14, l14 = hh(H, 14), ll(L, 14)
G['WILLIAMS_R'] = pts(pd.Series(np.where(h14 == l14, -50, -100 * (h14 - C) / (h14 - l14))).where(~h14.isna()))
ao = sma(HL2, 5) - sma(HL2, 34)
G['AO'] = {'value': pts(ao)}
e3t = ema(ema(ema(C, 15), 15), 15)
G['TRIX'] = pts(100 * e3t.diff() / e3t.shift(1))
pc = C.shift(1); bp = C - pd.concat([L, pc], axis=1).min(axis=1); trr = pd.concat([H, pc], axis=1).max(axis=1) - pd.concat([L, pc], axis=1).min(axis=1)
bp.iloc[0] = C[0] - L[0]; trr.iloc[0] = H[0] - L[0]
avg = lambda n: bp.rolling(n).sum() / trr.rolling(n).sum()
uo = 100 * (4 * avg(7) + 2 * avg(14) + avg(28)) / 7
uo[:28] = np.nan
G['ULTIMATE'] = pts(uo)
au, ad = [], []
for i in range(25, N):
    win_h = H[i - 25:i + 1].to_numpy(); win_l = L[i - 25:i + 1].to_numpy()
    hi = 25 - int(np.where(win_h == win_h.max())[0][-1]); lo = 25 - int(np.where(win_l == win_l.min())[0][-1])
    au.append([int(df.time[i]), 100 * (25 - hi) / 25]); ad.append([int(df.time[i]), 100 * (25 - lo) / 25])
G['AROON'] = {'up': au, 'down': ad}
d1 = C.diff(); su = d1.clip(lower=0).rolling(14).sum(); sd_ = (-d1).clip(lower=0).rolling(14).sum()
G['CMO'] = pts(pd.Series(np.where(su + sd_ == 0, 0, 100 * (su - sd_) / (su + sd_))).where(~su.isna()))
G['DPO'] = pts(C.shift(20 // 2 + 1) - sma(C, 20))
m = C.diff(); num = ema(ema(m, 25), 13); den = ema(ema(m.abs(), 25), 13)
tsi = pd.Series(np.where(den == 0, 0, 100 * num / den)).where(~den.isna())
G['TSI'] = {'tsi': pts(tsi), 'signal': pts(ema(tsi, 7))}
vp, vm = (H - L.shift(1)).abs(), (L - H.shift(1)).abs()
G['VORTEX'] = {'plus': pts(vp.rolling(14).sum() / tr().rolling(14).sum().where(lambda s: s.index >= 14)), 'minus': pts(vm.rolling(14).sum() / tr().rolling(14).sum().where(lambda s: s.index >= 14))}
# Fisher(10)
fish, trig = [], []; value = prev = 0.0
for i in range(9, N):
    w = HL2[i - 9:i + 1]; hi, lo = w.max(), w.min()
    value = .66 * ((.5 if hi == lo else (HL2[i] - lo) / (hi - lo)) - .5) + .67 * value
    value = max(-.999, min(.999, value))
    f = .5 * math.log((1 + value) / (1 - value)) + .5 * prev
    if i > 9: trig.append([int(df.time[i]), prev])
    fish.append([int(df.time[i]), f]); prev = f
G['FISHER'] = {'fisher': fish, 'trigger': trig}
e13 = ema(C, 13)
G['ELDER_RAY'] = {'bull': pts(H - e13), 'bear': pts(L - e13)}
bop = pd.Series(np.where(H == L, 0, (C - O) / (H - L)))
G['BOP'] = pts(sma(bop, 14))
f12, s26 = ema(C, 12), ema(C, 26); ppo = 100 * (f12 - s26) / s26; ps = ema(ppo, 9)
G['PPO'] = {'ppo': pts(ppo), 'signal': pts(ps), 'histogram': pts(ppo - ps)}
a22 = atr(22)
G['CHANDELIER'] = {'long': pts(hh(H, 22) - 3 * a22), 'short': pts(ll(L, 22) + 3 * a22)}
basis = sma(C, 20)
delta = C - ((hh(H, 20) + ll(L, 20)) / 2 + basis) / 2
G['SQUEEZE'] = {'momentum': pts(linreg_end(delta, 20)), 'squeeze': pts(basis * 0 + 0)}

print(json.dumps({'bars': bars, 'golden': G}, separators=(',', ':')))
