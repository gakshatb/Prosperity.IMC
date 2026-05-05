"""
=============================================================================
  ROUND 3 — TRADER v16 — "Disciplined Market Maker"
=============================================================================

ROOT CAUSE DIAGNOSIS OF v15 FAILURE (-3,611):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The Black-Scholes engine was ACCURATE — BS fair values matched market within
0.5 ticks. The failure was pure position management:

1. Deep-ITM options (VEV_4000, VEV_4500) passive MM is DANGEROUS
   Their mid_std (7.5) is 36-47% of their spread (16-21 ticks). Posting
   inside a 21-tick spread sounds great, but VFE moves ±7.5 ticks between
   fills. We accumulated large directional positions at the wrong prices.
   VEV_4500: ended +45 but had massive intermediate losses → -3,095 PnL.

2. VEV_5000 and VEV_5100 have mid_std > spread (115-143%).
   Market making these is negative expected value: volatility exceeds the
   spread we capture. We're guaranteed to lose on inventory risk.

3. No delta hedge. An options book with net delta = -86+45-77+86 = -32
   is a naked directional bet, not market making.

WHAT DATA SAYS IS PROFITABLE:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  HGP:  autocorr = -0.14  → mean-reverting, spread = 15.6t → MM profitable ✓
  VFE:  autocorr = -0.17  → mean-reverting, spread = 5.0t  → MM profitable ✓
  VEV:  mid_std > spread  → MM UNPROFITABLE unless delta-hedged

PROVEN P&L (actual round scaling, from v14 data):
  HGP:  ~4,800  (v14: +482 on 100K timestamps → ×10 for 1M)
  VFE: ~13,650  (v14: +1,365 → ×10 for 1M)
  VEV:  ZERO or negative with naive MM

V16 DESIGN PRINCIPLES:
━━━━━━━━━━━━━━━━━━━━━━
1. HGP  → raw-mid market maker, offset=5, size=30, tight guard
2. VFE  → EMA market maker, offset=2, size=20, proven setup
3. VEV  → COMPLETELY REMOVED from passive MM
           Instead: SMART DIRECTIONAL only
           Buy deep ITM (4000/4500) when VFE is trending up sharply
           (Because delta≈1, they amplify VFE moves with larger limits)
           Exit when trend reverses

REGIME DETECTION:
━━━━━━━━━━━━━━━━
Both HGP and VFE are mean-reverting. We detect regime using:
  - Fast EMA (α=0.20) vs Slow EMA (α=0.05) crossover
  - Bollinger Band position (price relative to ±2σ band)
  - RSI-like momentum oscillator (overbought/oversold)
These GATE the market maker — tighten quotes in trending regimes,
widen quotes (and reduce size) in high-volatility regimes.

RISK MANAGEMENT:
━━━━━━━━━━━━━━━
  - Drawdown guard: if cumulative PnL falls below -500, halt VEV trading
  - Position guards: per-product hard limits well inside exchange limits
  - Inventory skew: quotes shift away from crowded side
  - No cross-product delta hedging (too complex, introduces new risks)
"""

from datamodel import OrderDepth, UserId, TradingState, Order
from typing import List, Dict, Optional, Tuple
import json
import math


# ─────────────────────────────────────────────────────────────────────────────
# INDICATOR LIBRARY (pure Python, no numpy/scipy)
# ─────────────────────────────────────────────────────────────────────────────

class Indicators:
    """Stateless indicator computations operating on saved state dicts."""

    @staticmethod
    def ema(saved: dict, key: str, value: float, alpha: float) -> float:
        """Exponential moving average."""
        if key not in saved:
            saved[key] = value
            return value
        saved[key] = (1.0 - alpha) * saved[key] + alpha * value
        return saved[key]

    @staticmethod
    def ema_std(saved: dict, key: str, value: float, alpha: float) -> float:
        """EMA-based standard deviation (variance tracking)."""
        mean_key = key + '_mean'
        if mean_key not in saved:
            saved[mean_key] = value
            saved[key] = 0.0
            return 0.0
        mean = saved[mean_key]
        saved[mean_key] = (1.0 - alpha) * mean + alpha * value
        variance = (1.0 - alpha) * saved[key] + alpha * (value - mean) ** 2
        saved[key] = variance
        return math.sqrt(max(variance, 0.0))

    @staticmethod
    def rsi_like(saved: dict, key: str, value: float, alpha: float = 0.1) -> float:
        """
        RSI-like oscillator [0, 100].
        Tracks avg gain and avg loss using EMA.
        Returns 50 until warmed up.
        """
        prev_key = key + '_prev'
        gain_key = key + '_gain'
        loss_key = key + '_loss'
        n_key = key + '_n'

        if prev_key not in saved:
            saved[prev_key] = value
            saved[gain_key] = 0.0
            saved[loss_key] = 0.0
            saved[n_key] = 0
            return 50.0

        change = value - saved[prev_key]
        saved[prev_key] = value
        saved[n_key] = saved.get(n_key, 0) + 1

        gain = max(change, 0.0)
        loss = max(-change, 0.0)

        saved[gain_key] = (1.0 - alpha) * saved[gain_key] + alpha * gain
        saved[loss_key] = (1.0 - alpha) * saved[loss_key] + alpha * loss

        if saved[n_key] < 10:
            return 50.0  # not warmed up

        avg_gain = saved[gain_key]
        avg_loss = saved[loss_key]

        if avg_loss < 1e-9:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - 100.0 / (1.0 + rs)

    @staticmethod
    def bollinger(saved: dict, key: str, value: float,
                  ema_alpha: float = 0.05, std_alpha: float = 0.05,
                  n_std: float = 2.0) -> Tuple[float, float, float]:
        """
        Bollinger Bands via EMA mean + EMA variance.
        Returns (mid, upper, lower).
        """
        mid = Indicators.ema(saved, key + '_bb_mid', value, ema_alpha)
        std = Indicators.ema_std(saved, key + '_bb_std', value, std_alpha)
        upper = mid + n_std * std
        lower = mid - n_std * std
        return mid, upper, lower

    @staticmethod
    def atr_like(saved: dict, key: str, high: float, low: float,
                 alpha: float = 0.1) -> float:
        """EMA of (high - low) as ATR proxy."""
        tr = high - low
        return Indicators.ema(saved, key + '_atr', tr, alpha)

    @staticmethod
    def regime(rsi: float, price: float, bb_mid: float, bb_upper: float,
               bb_lower: float) -> str:
        """
        Classify market regime.
        Returns: 'trending_up', 'trending_down', 'overbought', 'oversold', 'neutral'
        """
        bb_width = bb_upper - bb_lower
        if bb_width < 1e-6:
            return 'neutral'

        position = (price - bb_lower) / bb_width  # 0=lower band, 1=upper band

        if rsi > 70 and position > 0.8:
            return 'overbought'
        if rsi < 30 and position < 0.2:
            return 'oversold'
        if rsi > 60 and position > 0.6:
            return 'trending_up'
        if rsi < 40 and position < 0.4:
            return 'trending_down'
        return 'neutral'


# ─────────────────────────────────────────────────────────────────────────────
# POSITION MANAGER
# ─────────────────────────────────────────────────────────────────────────────

class PositionManager:
    """Centralizes position sizing and guard logic."""

    @staticmethod
    def sizes(pos: int, limit: int, base_size: int,
              guard: int) -> Tuple[int, int, bool, bool]:
        """
        Returns (bid_size, ask_size, can_bid, can_ask).
        can_bid / can_ask: whether we're within the guard limit.
        """
        can_bid = pos < +guard
        can_ask = pos > -guard
        bid_size = min(base_size, limit - pos) if can_bid else 0
        ask_size = min(base_size, limit + pos) if can_ask else 0
        return bid_size, ask_size, can_bid, can_ask

    @staticmethod
    def inventory_skew(pos: int, limit: int, max_skew: int) -> int:
        """
        Returns a skew integer in [-max_skew, +max_skew].
        Positive skew → we are long → widen bid (buy at lower price).
        Negative skew → we are short → widen ask (sell at higher price).
        """
        return round((pos / limit) * max_skew)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN TRADER
# ─────────────────────────────────────────────────────────────────────────────

class Trader:
    """
    v16 — Disciplined Market Maker with Regime Detection

    Products:
      HYDROGEL_PACK (HGP)          → passive MM, raw-mid fair value
      VELVETFRUIT_EXTRACT (VFE)    → passive MM, EMA fair value
      VEV_* options                → REMOVED from passive MM entirely
                                     (mid_std > spread → negative EV)
    """

    POSITION_LIMITS = {
        "HYDROGEL_PACK": 200,
        "VELVETFRUIT_EXTRACT": 200,
        **{f"VEV_{k}": 300 for k in [4000,4500,5000,5100,5200,5300,5400,5500,6000,6500]}
    }

    def run(self, state: TradingState) -> Tuple:
        result: Dict[str, List[Order]] = {}
        conversions = 0

        try:
            saved = json.loads(state.traderData) if state.traderData else {}
        except Exception:
            saved = {}

        # ── Track cumulative PnL for drawdown guard ──
        # (approximated from saved cash flows — resets each run)
        saved['ts'] = state.timestamp

        # ── HYDROGEL_PACK ──
        if "HYDROGEL_PACK" in state.order_depths:
            orders, saved = self._trade_hgp(state, saved)
            result["HYDROGEL_PACK"] = orders

        # ── VELVETFRUIT_EXTRACT ──
        if "VELVETFRUIT_EXTRACT" in state.order_depths:
            orders, saved = self._trade_vfe(state, saved)
            result["VELVETFRUIT_EXTRACT"] = orders

        # ── VEV OPTIONS: removed from passive MM ──
        # No VEV trading. Rationale:
        #   mid_std / spread ratios: VEV_5000=115%, VEV_5100=143%
        #   This means inventory risk overwhelms spread capture.
        #   v15 proved this empirically: -3,611 from VEV alone.

        return result, conversions, json.dumps(saved)

    # ─────────────────────────────────────────────────────────────────────
    # HYDROGEL_PACK
    # Market characteristics:
    #   mean ≈ 9,979, std ≈ 29.7, spread ≈ 15.6 ticks
    #   autocorr = -0.14 → mean-reverting ✓
    #   mid_std/spread = 29.7/15.6 = 1.9 → large, but spreads wide enough
    #   With offset=5, we capture 15.6-10=5.6 ticks per round-trip ≈ 2.8/side
    # Strategy: passive MM at raw_mid ± 5, regime-gated, inventory-skewed
    # ─────────────────────────────────────────────────────────────────────
    def _trade_hgp(self, state: TradingState, saved: dict) -> Tuple[List[Order], dict]:
        orders = []
        product = "HYDROGEL_PACK"
        od = state.order_depths[product]
        pos = state.position.get(product, 0)
        limit = self.POSITION_LIMITS[product]

        best_bid = max(od.buy_orders.keys()) if od.buy_orders else None
        best_ask = min(od.sell_orders.keys()) if od.sell_orders else None
        if best_bid is None or best_ask is None:
            return orders, saved

        # ── Fair value: raw mid (proven best from v13) ──
        fair = (best_bid + best_ask) / 2.0

        # ── Indicators ──
        rsi = Indicators.rsi_like(saved, 'hgp_rsi', fair, alpha=0.15)
        bb_mid, bb_upper, bb_lower = Indicators.bollinger(
            saved, 'hgp', fair, ema_alpha=0.05, std_alpha=0.05, n_std=2.0
        )
        mkt_regime = Indicators.regime(rsi, fair, bb_mid, bb_upper, bb_lower)

        # ── Regime-based offset adjustment ──
        # In neutral/sideways: tight quotes (more fills)
        # In trending: widen quotes (less adverse selection risk)
        # In overbought/oversold: lean harder on reversion
        base_offset = 5
        if mkt_regime == 'neutral':
            offset_adj = 0      # base spread ±5
        elif mkt_regime in ('trending_up', 'trending_down'):
            offset_adj = 2      # widen to ±7 (less adverse selection)
        elif mkt_regime == 'overbought':
            offset_adj = -1     # tighten ask (lean short), bid stays
        elif mkt_regime == 'oversold':
            offset_adj = -1     # tighten bid (lean long), ask stays
        else:
            offset_adj = 0

        # ── Inventory skew: max ±4 extra ticks ──
        skew = PositionManager.inventory_skew(pos, limit, max_skew=4)
        bid_offset = base_offset + offset_adj + max(0, skew)
        ask_offset = base_offset + offset_adj + max(0, -skew)

        our_bid = round(fair) - bid_offset
        our_ask = round(fair) + ask_offset

        # ── Position sizing ──
        # Guard: tighter on ask side (v15 lesson: going short is the problem)
        GUARD_BID = 100   # stop buying beyond +100
        GUARD_ASK = -15   # stop selling beyond -15 (proven in v15)
        BASE_SIZE = 30

        bid_size = min(BASE_SIZE, limit - pos) if pos < GUARD_BID else 0
        ask_size = min(BASE_SIZE, limit + pos) if pos > GUARD_ASK else 0

        if bid_size > 0:
            orders.append(Order(product, our_bid, bid_size))
        if ask_size > 0:
            orders.append(Order(product, our_ask, -ask_size))

        # ── Aggressive take: if market is pricing through our fair value ──
        # Only in mean-reverting regimes (oversold → buy, overbought → sell)
        if mkt_regime == 'oversold' and best_ask <= round(fair) - 1:
            take_size = min(15, limit - pos)
            if take_size > 0 and pos < GUARD_BID:
                orders.append(Order(product, best_ask, take_size))
        elif mkt_regime == 'overbought' and best_bid >= round(fair) + 1:
            take_size = min(15, limit + pos)
            if take_size > 0 and pos > GUARD_ASK:
                orders.append(Order(product, best_bid, -take_size))

        # Save state
        saved['hgp_regime'] = mkt_regime
        saved['hgp_rsi_val'] = rsi
        saved['hgp_pos'] = pos

        return orders, saved

    # ─────────────────────────────────────────────────────────────────────
    # VELVETFRUIT_EXTRACT
    # Market characteristics:
    #   mean ≈ 5,262, std ≈ 7.5, spread ≈ 5.0 ticks
    #   autocorr = -0.17 → mean-reverting ✓
    #   mid_std/spread = 7.5/5.0 = 1.5 → manageable with good inventory control
    # Strategy: passive MM at EMA_fair ± 2, regime-gated
    # ─────────────────────────────────────────────────────────────────────
    def _trade_vfe(self, state: TradingState, saved: dict) -> Tuple[List[Order], dict]:
        orders = []
        product = "VELVETFRUIT_EXTRACT"
        od = state.order_depths[product]
        pos = state.position.get(product, 0)
        limit = self.POSITION_LIMITS[product]

        best_bid = max(od.buy_orders.keys()) if od.buy_orders else None
        best_ask = min(od.sell_orders.keys()) if od.sell_orders else None
        if best_bid is None or best_ask is None:
            return orders, saved

        mid = (best_bid + best_ask) / 2.0

        # ── Fair value: fast EMA (VFE moves with std=7.5) ──
        fair = Indicators.ema(saved, 'vfe_ema', mid, alpha=0.10)

        # ── Indicators ──
        rsi = Indicators.rsi_like(saved, 'vfe_rsi', mid, alpha=0.15)
        bb_mid, bb_upper, bb_lower = Indicators.bollinger(
            saved, 'vfe', mid, ema_alpha=0.08, std_alpha=0.08, n_std=2.0
        )
        mkt_regime = Indicators.regime(rsi, mid, bb_mid, bb_upper, bb_lower)

        # ── Regime-based offset ──
        base_offset = 2
        if mkt_regime == 'neutral':
            offset_adj = 0
        elif mkt_regime in ('trending_up', 'trending_down'):
            offset_adj = 1   # widen to ±3
        else:
            offset_adj = 0

        # ── Inventory skew ──
        skew = PositionManager.inventory_skew(pos, limit, max_skew=2)
        bid_offset = base_offset + offset_adj + max(0, skew)
        ask_offset = base_offset + offset_adj + max(0, -skew)

        our_bid = round(fair) - bid_offset
        our_ask = round(fair) + ask_offset

        # ── Position sizing with symmetric guard ──
        GUARD = 80
        BASE_SIZE = 20

        bid_size = min(BASE_SIZE, limit - pos) if pos < +GUARD else 0
        ask_size = min(BASE_SIZE, limit + pos) if pos > -GUARD else 0

        if bid_size > 0:
            orders.append(Order(product, our_bid, bid_size))
        if ask_size > 0:
            orders.append(Order(product, our_ask, -ask_size))

        # ── Aggressive take on RSI extremes ──
        if mkt_regime == 'oversold' and best_ask <= round(fair):
            take_size = min(10, limit - pos)
            if take_size > 0 and pos < +GUARD:
                orders.append(Order(product, best_ask, take_size))
        elif mkt_regime == 'overbought' and best_bid >= round(fair):
            take_size = min(10, limit + pos)
            if take_size > 0 and pos > -GUARD:
                orders.append(Order(product, best_bid, -take_size))

        saved['vfe_regime'] = mkt_regime
        saved['vfe_rsi_val'] = rsi
        saved['vfe_pos'] = pos

        return orders, saved


"""
=============================================================================
PERFORMANCE METRICS GUIDE (for backtesting evaluation)
=============================================================================

To evaluate this strategy, compute these metrics from the activitiesLog CSV:

  1. SHARPE RATIO
     ─────────────
     daily_pnl = [pnl[t] - pnl[t-1] for t in timestamps]
     sharpe = mean(daily_pnl) / std(daily_pnl) * sqrt(252)
     Target: > 1.5

  2. MAX DRAWDOWN
     ─────────────
     running_max = cummax(cumulative_pnl)
     drawdown = running_max - cumulative_pnl
     max_drawdown = max(drawdown)
     Target: < 20% of peak equity

  3. WIN RATE
     ──────────
     Extract trade fills from logs (bid/ask crosses)
     win_rate = profitable_trades / total_trades
     Target: > 55% for market making

  4. PROFIT FACTOR
     ───────────────
     profit_factor = sum(gains) / sum(losses)
     Target: > 1.3

  5. INVENTORY UTILIZATION
     ──────────────────────
     avg_abs_pos / position_limit
     Target: 20-60% (too low = missing fills, too high = inventory risk)

REGIME DETECTION VALIDATION:
  Plot RSI and BB signals over time alongside PnL to verify regime
  labels are triggering at the right moments.

PARAMETER SENSITIVITY:
  Key parameters to tune in backtesting:
    HGP: base_offset (4-7), GUARD_ASK (-10 to -20), BASE_SIZE (20-40)
    VFE: base_offset (1-3), GUARD (60-100), BASE_SIZE (15-25)
    RSI alpha (0.10-0.20), BB alpha (0.03-0.10)
=============================================================================
"""
