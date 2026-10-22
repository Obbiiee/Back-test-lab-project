"""Authored OHLC/context tests; no actual source rights or market acceptance."""
from dataclasses import replace
import unittest
from market_data.context_warmup import IndicatorSpec as I, ContextBar as B, plan_warmup, completed_context

NS = 1000000000

def bar(index, timeframe=60):
    return B(index*timeframe*NS, (index+1)*timeframe*NS, '10.000', '12.000', '9.000', '11.000')


class WarmupTests(unittest.TestCase):
    def test_finite_lookbacks_and_timeframe_union(self):
        plans=plan_warmup([I('SMA',60,period=200),I('BOLLINGER',60,period=20),I('STOCHASTIC',300,k_period=14,d_period=3)],buffer_bars=5)
        self.assertEqual([(p.timeframe_seconds,p.required_bars) for p in plans],[(60,205),(300,21)])
        self.assertEqual(plan_warmup([]),())

    def test_ema_seed_error_measured_against_independent_recurrence(self):
        for period in [1,12,200,1000]:
            p=plan_warmup([I('EMA',60,period=period)],seed_decay_tolerance=1e-6)[0]
            a,b=500.,700.
            for i in range(p.required_bars-period):
                x=100.+(i%7);alpha=2/(period+1)
                a=alpha*x+(1-alpha)*a;b=alpha*x+(1-alpha)*b
            if period==1:a=b=100.
            self.assertLessEqual(abs(a-b),200e-6+1e-10)
            self.assertIn('NOT_CONVERGENCE',p.basis)
        self.assertGreater(plan_warmup([I('EMA',60,period=200)])[0].required_bars,1000)

    def test_recursive_and_macd_not_universal_count(self):
        ema=plan_warmup([I('EMA',60,period=14)])[0].required_bars
        rsi=plan_warmup([I('RSI',60,period=14)])[0].required_bars
        atr=plan_warmup([I('ATR',60,period=14)])[0].required_bars
        self.assertGreater(rsi,ema);self.assertEqual(rsi,atr)
        self.assertEqual(plan_warmup([I('ATR',60,period=1)])[0].required_bars,2)
        loose=plan_warmup([I('MACD',60)],seed_decay_tolerance=1e-3)[0]
        strict=plan_warmup([I('MACD',60)],seed_decay_tolerance=1e-9)[0]
        self.assertGreater(strict.required_bars,loose.required_bars)
        # Independently evolve normalized seed differences in fast/slow/signal.
        fast,slow,signal=1.,-1.,1.
        for _ in range(strict.required_bars-26):
            fast*=1-2/13;slow*=1-2/27
            signal=(2/10)*(fast-slow)+(1-2/10)*signal
        self.assertLess(abs(signal),1e-9)

    def test_cutoff_closed_boundary_and_future_mutation_invariance(self):
        p=plan_warmup([I('SMA',60,period=2)])[0]
        past=[bar(0),bar(1),bar(2)]
        a=completed_context(past+[bar(3)],p,trusted_start_ns=180*NS)
        b=completed_context(past+[replace(bar(3),open='NaN',high='future'),bar(4)],p,trusted_start_ns=180*NS)
        self.assertEqual(a,b);self.assertEqual(a.candles,(bar(1),bar(2)))
        self.assertEqual(a.state,'SUFFICIENT_COUNT');self.assertFalse(a.execution_authority)
        self.assertEqual(a.candles[-1].close_ns,180*NS)

    def test_incomplete_gaps_and_no_interpolation(self):
        p=plan_warmup([I('SMA',60,period=4)])[0]
        r=completed_context([bar(0),bar(3)],p,trusted_start_ns=240*NS)
        self.assertEqual(r.state,'WARMUP_INCOMPLETE');self.assertEqual(r.available_bars,2)
        self.assertEqual(r.candles,(bar(0),bar(3)))
        self.assertEqual(completed_context([],p,trusted_start_ns=0).state,'WARMUP_INCOMPLETE')

    def test_utc_daily_alignment_and_cross_frame_cutoff(self):
        cutoff=86400*NS
        for frame in [60,300,3600,86400]:
            p=plan_warmup([I('SMA',frame,period=1)])[0]
            rows=[bar(86400//frame-1,frame),bar(86400//frame,frame)]
            r=completed_context(rows,p,trusted_start_ns=cutoff)
            self.assertEqual(len(r.candles),1);self.assertEqual(r.candles[0].close_ns,cutoff)

    def test_reject_untrusted_geometry_prices_and_parameters(self):
        p=plan_warmup([I('SMA',60,period=2)])[0]
        for rows in [[bar(1),bar(0)],[bar(0),bar(0)],[replace(bar(0),open_ns=1)],[replace(bar(0),high='8')],[replace(bar(0),close='NaN')]]:
            with self.assertRaises(ValueError):completed_context(rows,p,trusted_start_ns=180*NS)
        for spec in [I('EMA',True),I('UNKNOWN',60),I('SMA',60,period=True),I('MACD',60,fast_period=26,slow_period=12),I('SMA',604800)]:
            with self.assertRaises(ValueError):plan_warmup([spec])
        for tolerance in [True,0,float('nan'),1e-20]:
            with self.assertRaises(ValueError):plan_warmup([I('EMA',60)],seed_decay_tolerance=tolerance)
        with self.assertRaises(ValueError):completed_context([],p,trusted_start_ns=True)
        with self.assertRaises(ValueError):plan_warmup([I('SMA',60)]*129)

if __name__=='__main__':unittest.main()
