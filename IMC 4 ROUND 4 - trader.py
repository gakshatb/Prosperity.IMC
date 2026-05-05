"""
Round 4 Trading Strategy
========================
Assets: HYDROGEL_PACK (HP), VELVETFRUIT_EXTRACT (VE), VELVETFRUIT_EXTRACT_VOUCHERs (VEVs)

Key Insights from Data Analysis:
---------------------------------
COUNTERPARTIES:
  Mark 14 & 38 → Market Makers for HP; Mark 14 also for VE and VEV_4000
  Mark 55       → Market Maker for VE (very active, ~1200 trades)
  Mark 01       → Aggressive OTM CALL BUYER (VEV_5200 to VEV_6500); buys throughout the day
  Mark 22       → Aggressive OTM CALL SELLER (mirror of Mark 01); sells to him
  Mark 67       → Informed directional BUYER of VE (only buys, never sells; +2.85 tick drift after buys)
  Mark 49       → Small bearish participant on VE

PRICE CHARACTERISTICS:
  HP:  Fair value ~10000, mean-reverting, std~34, autocorr=-0.12
  VE:  Fair value ~5248, mean-reverting, std~18, autocorr=-0.16
  VEV: Implied vol ~24%, well-priced; OTM calls systematically mispriced (Mark 01 overpays)

STRATEGY PER ASSET:
  HP:  Market-making around fair value 10000 ± dynamic band
  VE:  Market-making + tilt long when Mark 67 is buying
  VEV: Sell OTM calls at ask (compete with Mark 22 / sell to Mark 01)
       Especially VEV_5300, VEV_5400, VEV_5500 — liquid, mispriced, good spread
"""

from datamodel import (
    OrderDepth, TradingState, Order, Symbol, Trade,
    Listing, Observation, Product, Position, UserId
)
from typing import Dict, List, Tuple, Optional
import math

# ─── Constants ────────────────────────────────────────────────────────────────

HYDROGEL_PACK = "HYDROGEL_PACK"
VELVETFRUIT_EXTRACT = "VELVETFRUIT_EXTRACT"
VELVETFRUIT_EXTRACT_VOUCHER = "VELVETFRUIT_EXTRACT_VOUCHER"

# Position limits
LIMITS = {
    HYDROGEL_PACK: 200,
    VELVETFRUIT_EXTRACT: 200,
    "VEV_4000": 300, "VEV_4500": 300, "VEV_5000": 300,
    "VEV_5100": 300, "VEV_5200": 300, "VEV_5300": 300,
    "VEV_5400": 300, "VEV_5500": 300, "VEV_6000": 300,
    "VEV_6500": 300,
}

# VEV strikes
VEV_STRIKES = {
    "VEV_4000": 4000, "VEV_4500": 4500, "VEV_5000": 5000,
    "VEV_5100": 5100, "VEV_5200": 5200, "VEV_5300": 5300,
    "VEV_5400": 5400, "VEV_5500": 5500, "VEV_6000": 6000,
    "VEV_6500": 6500,
}

# Mark 01 pays up for OTM calls — these are our best targets to SELL
VEV_SELL_TARGETS = {"VEV_5300", "VEV_5400", "VEV_5500", "VEV_6000", "VEV_6500"}

# Informed trader IDs
INFORMED_BUYERS = {"Mark 67"}    # consistently bullish on VE
BEARISH_PARTICIPANTS = {"Mark 49"}


# ─── Helper: Black-Scholes for VEV fair value ─────────────────────────────────

def norm_cdf(x: float) -> float:
    """Approximation of standard normal CDF."""
    t = 1.0 / (1.0 + 0.2316419 * abs(x))
    poly = t * (0.319381530 + t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))))
    cdf = 1.0 - (1.0 / math.sqrt(2 * math.pi)) * math.exp(-0.5 * x * x) * poly
    return cdf if x >= 0 else 1.0 - cdf


def bs_call_price(S: float, K: float, T: float, sigma: float = 0.25) -> float:
    """Black-Scholes call price (r=0)."""
    if T <= 0:
        return max(S - K, 0.0)
    if sigma <= 0 or S <= 0:
        return max(S - K, 0.0)
    d1 = (math.log(S / K) + 0.5 * sigma * sigma * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return S * norm_cdf(d1) - K * norm_cdf(d2)


# ─── State Tracker ────────────────────────────────────────────────────────────

class StateTracker:
    """Tracks EWMA prices, counterparty signals, and position helpers."""

    def __init__(self):
        self.hp_ewma: float = 10000.0
        self.ve_ewma: float = 5248.0
        self.hp_alpha: float = 0.05
        self.ve_alpha: float = 0.05

        self.informed_buy_signal: int = 0   # +1 if Mark 67 bought recently
        self.last_mark67_ts: int = -9999
        self.signal_decay: int = 2000       # timestamps signal stays active

        self.tick: int = 0

    def update(self, state: TradingState):
        """Update internal state from TradingState."""
        self.tick += 1

        # Update HP EWMA
        if HYDROGEL_PACK in state.order_depths:
            mid = self._mid_price(state.order_depths[HYDROGEL_PACK])
            if mid is not None:
                self.hp_ewma = (1 - self.hp_alpha) * self.hp_ewma + self.hp_alpha * mid

        # Update VE EWMA
        if VELVETFRUIT_EXTRACT in state.order_depths:
            mid = self._mid_price(state.order_depths[VELVETFRUIT_EXTRACT])
            if mid is not None:
                self.ve_ewma = (1 - self.ve_alpha) * self.ve_ewma + self.ve_alpha * mid

        # Detect Mark 67 buys in recent trades
        for product, trades in state.market_trades.items():
            if product == VELVETFRUIT_EXTRACT:
                for trade in trades:
                    if trade.buyer in INFORMED_BUYERS:
                        self.last_mark67_ts = state.timestamp

        self.informed_buy_signal = (
            1 if (state.timestamp - self.last_mark67_ts) < self.signal_decay else 0
        )

    def _mid_price(self, od: OrderDepth) -> Optional[float]:
        if od.buy_orders and od.sell_orders:
            best_bid = max(od.buy_orders.keys())
            best_ask = min(od.sell_orders.keys())
            return (best_bid + best_ask) / 2.0
        elif od.buy_orders:
            return float(max(od.buy_orders.keys()))
        elif od.sell_orders:
            return float(min(od.sell_orders.keys()))
        return None


# ─── Market Making Helpers ────────────────────────────────────────────────────

def get_position(state: TradingState, product: str) -> int:
    return state.position.get(product, 0)


def make_orders_mean_revert(
    product: str,
    fair_value: float,
    spread_half: float,
    position: int,
    limit: int,
    order_depth: OrderDepth,
    skew_per_unit: float = 0.02,
    max_clip: int = 20,
) -> List[Order]:
    """
    Market-making strategy with inventory skew.
    - Posts bid below fair value, ask above fair value
    - Skews quotes based on current position to manage inventory
    - Aggressively takes favourable orders in the book
    """
    orders: List[Order] = []
    pos = position

    # Position skew: tighten on the side we want to reduce
    skew = pos * skew_per_unit
    bid_price = int(fair_value - spread_half - skew)
    ask_price = int(fair_value + spread_half - skew)

    # Aggress existing book (take orders better than our fair value)
    if order_depth.sell_orders:
        for ask, vol in sorted(order_depth.sell_orders.items()):
            if ask < fair_value - 1 and pos < limit:
                buy_qty = min(-vol, limit - pos, max_clip)
                if buy_qty > 0:
                    orders.append(Order(product, ask, buy_qty))
                    pos += buy_qty

    if order_depth.buy_orders:
        for bid, vol in sorted(order_depth.buy_orders.items(), reverse=True):
            if bid > fair_value + 1 and pos > -limit:
                sell_qty = min(vol, pos + limit, max_clip)
                if sell_qty > 0:
                    orders.append(Order(product, bid, -sell_qty))
                    pos -= sell_qty

    # Post passive quotes
    passive_bid_qty = min(limit - pos, 15)
    passive_ask_qty = min(pos + limit, 15)
    if passive_bid_qty > 0:
        orders.append(Order(product, bid_price, passive_bid_qty))
    if passive_ask_qty > 0:
        orders.append(Order(product, ask_price, -passive_ask_qty))

    return orders


# ─── VEV Strategy ─────────────────────────────────────────────────────────────

def vev_strategy(
    product: str,
    strike: float,
    spot: float,
    tte_days: float,
    position: int,
    limit: int,
    order_depth: OrderDepth,
    implied_vol: float = 0.25,
    sell_premium_frac: float = 0.05,
) -> List[Order]:
    """
    VEV option strategy:
    - For VEV_5300 to VEV_6500 (OTM calls Mark 01 loves to buy):
        SELL at market ask or a touch above BS fair value (collect premium)
    - For deep ITM (VEV_4000): Market-make the spread (Mark 14/38 style)
    - For near-money: cautious market-making

    sell_premium_frac: how much above BS value we demand before selling
    """
    orders: List[Order] = []

    T = tte_days / 252.0
    fair = bs_call_price(spot, strike, T, implied_vol)

    # Deep OTM: Mark 01 buys at essentially zero — avoid holding them short at 0
    if fair < 0.5:
        return orders

    # For OTM call targets: primarily SELL
    if product in VEV_SELL_TARGETS:
        min_sell_price = max(1, int(fair * (1 + sell_premium_frac)))

        # Aggress bids that are above our minimum sell price
        if order_depth.buy_orders:
            for bid, vol in sorted(order_depth.buy_orders.items(), reverse=True):
                if bid >= min_sell_price and position > -limit:
                    sell_qty = min(vol, position + limit, 25)
                    if sell_qty > 0:
                        orders.append(Order(product, bid, -sell_qty))
                        position -= sell_qty

        # Post ask just above fair value
        if order_depth.sell_orders:
            best_ask = min(order_depth.sell_orders.keys())
            post_ask = min(best_ask, min_sell_price)
        else:
            post_ask = min_sell_price

        passive_qty = min(position + limit, 25)
        if passive_qty > 0:
            orders.append(Order(product, post_ask, -passive_qty))

    else:
        # For ATM/ITM options (VEV_4000, VEV_5000): Market-make the spread
        spread_half = max(2, int(fair * 0.008))
        bid_price = int(fair - spread_half)
        ask_price = int(fair + spread_half)

        # Aggress underpriced asks
        if order_depth.sell_orders:
            for ask, vol in sorted(order_depth.sell_orders.items()):
                if ask < fair - 2 and position < limit:
                    buy_qty = min(-vol, limit - position, 15)
                    if buy_qty > 0:
                        orders.append(Order(product, ask, buy_qty))
                        position += buy_qty

        # Aggress overpriced bids
        if order_depth.buy_orders:
            for bid, vol in sorted(order_depth.buy_orders.items(), reverse=True):
                if bid > fair + 2 and position > -limit:
                    sell_qty = min(vol, position + limit, 15)
                    if sell_qty > 0:
                        orders.append(Order(product, bid, -sell_qty))
                        position -= sell_qty

        if limit - position > 0:
            orders.append(Order(product, bid_price, min(limit - position, 10)))
        if position + limit > 0:
            orders.append(Order(product, ask_price, -min(position + limit, 10)))

    return orders


# ─── Main Trader Class ────────────────────────────────────────────────────────

class Trader:
    def __init__(self):
        self.tracker = StateTracker()

        # VEV TTE: starts at 7 Solvenarian days on day 1 of the round
        # Round 4 is the 2nd of the Great Orbital Ascension Trials
        # Image says VEV_5000 TTE=4 in round 4
        # We'll track approximate TTE decreasing each round-day
        self.base_tte = 4.0   # as given in the problem for round 4
        self.day_estimate = 1  # incremented by timestamp logic
        self._last_ts_bucket = -1

    def _estimate_tte(self, timestamp: int, day: int) -> float:
        """Estimate TTE in trading days based on elapsed time."""
        # TTE decreases by 1 each Solvenarian day
        # Each trading day has ~1,000,000 timestamp ticks
        elapsed_days = (timestamp / 1_000_000)
        tte = max(0.5, self.base_tte - elapsed_days)
        return tte

    def run(self, state: TradingState) -> Tuple[Dict[str, List[Order]], int, str]:
        self.tracker.update(state)

        result: Dict[str, List[Order]] = {}
        conversions = 0
        trader_data = ""

        # ── Estimate current day / TTE ──────────────────────────────────────
        ts = state.timestamp
        tte = self._estimate_tte(ts, self.day_estimate)

        hp_fair = self.tracker.hp_ewma
        ve_fair = self.tracker.ve_ewma

        # ── HYDROGEL_PACK: Market-make around fair value ~10000 ──────────────
        if HYDROGEL_PACK in state.order_depths:
            hp_pos = get_position(state, HYDROGEL_PACK)
            hp_orders = make_orders_mean_revert(
                product=HYDROGEL_PACK,
                fair_value=hp_fair,
                spread_half=3,
                position=hp_pos,
                limit=LIMITS[HYDROGEL_PACK],
                order_depth=state.order_depths[HYDROGEL_PACK],
                skew_per_unit=0.015,
                max_clip=25,
            )
            result[HYDROGEL_PACK] = hp_orders

        # ── VELVETFRUIT_EXTRACT: Market-make + informed-buyer tilt ───────────
        if VELVETFRUIT_EXTRACT in state.order_depths:
            ve_pos = get_position(state, VELVETFRUIT_EXTRACT)

            # Tilt fair value up slightly when Mark 67 is active
            ve_fair_adjusted = ve_fair + (2.0 * self.tracker.informed_buy_signal)

            ve_orders = make_orders_mean_revert(
                product=VELVETFRUIT_EXTRACT,
                fair_value=ve_fair_adjusted,
                spread_half=2,
                position=ve_pos,
                limit=LIMITS[VELVETFRUIT_EXTRACT],
                order_depth=state.order_depths[VELVETFRUIT_EXTRACT],
                skew_per_unit=0.015,
                max_clip=20,
            )
            result[VELVETFRUIT_EXTRACT] = ve_orders

        # ── VEV OPTIONS: Sell OTM calls, market-make ITM/ATM ─────────────────
        for vev_product, strike in VEV_STRIKES.items():
            if vev_product not in state.order_depths:
                continue

            vev_pos = get_position(state, vev_product)
            vev_od = state.order_depths[vev_product]

            vev_orders = vev_strategy(
                product=vev_product,
                strike=float(strike),
                spot=ve_fair,
                tte_days=tte,
                position=vev_pos,
                limit=LIMITS.get(vev_product, 300),
                order_depth=vev_od,
                implied_vol=0.25,
                sell_premium_frac=0.04,   # sell at 4% above BS value
            )
            if vev_orders:
                result[vev_product] = vev_orders

        return result, conversions, trader_data
