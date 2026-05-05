"""
Round 5 Trading Strategy — "The Final Stretch"
"""

from datamodel import OrderDepth, TradingState, Order
from typing import Dict, List, Tuple, Optional

# ─── Configuration ────────────────────────────────────────────────────────────

# Momentum products: confirmed consistent trend across all 3 historical days.
# direction = +1 → hold LONG (price consistently rises each day)
# direction = -1 → hold SHORT (price consistently falls each day)
MOMENTUM: Dict[str, int] = {
    "MICROCHIP_OVAL":              -1,   # -744, -1824, -1897 per day → SHORT
    "PEBBLES_XS":                  -1,   # -1951, -1203,  -823 per day → SHORT
    "OXYGEN_SHAKE_GARLIC":         +1,   # +1828,  +111, +1958 per day → LONG
    "GALAXY_SOUNDS_BLACK_HOLES":   +1,   # +1446,  +688, +1320 per day → LONG
    "UV_VISOR_AMBER":              -1,   # -1499, -1109,  -255 per day → SHORT
    "PANEL_2X4":                   +1,   #  +738,  +738,  +894 per day → LONG
    "PEBBLES_S":                   -1,   #  -840,  -177,  -937 per day → SHORT
    "UV_VISOR_RED":                +1,   #  +842,  +182,  +698 per day → LONG
}

LIMIT = 10


# ─── Utilities ────────────────────────────────────────────────────────────────

def _pos(state: TradingState, product: str) -> int:
    return state.position.get(product, 0)


# ─── Momentum Strategy ────────────────────────────────────────────────────────

def momentum_orders(
    product:   str,
    direction: int,
    position:  int,
    od:        OrderDepth,
) -> List[Order]:
    """
    Reach and maintain the maximum position in the trend direction.

    LONG (direction=+1): target position = +LIMIT
    SHORT (direction=-1): target position = -LIMIT

    Execution priority:
      1. Aggress existing book: take all available liquidity toward our target.
      2. If still not at limit: post a passive order inside the spread to
         attract fills quickly without paying the full spread.

    We deliberately do NOT post quotes on the opposite side — this would
    counterproductively reduce our directional position.
    """
    orders: List[Order] = []

    if direction == +1:
        # ── LONG: need to buy up to +LIMIT ───────────────────────────────────
        remaining = LIMIT - position
        if remaining <= 0:
            return orders   # already at limit

        # Step 1: Aggress the ask side — take what's available
        if od.sell_orders:
            for ask, vol in sorted(od.sell_orders.items()):
                if remaining <= 0:
                    break
                qty = min(-vol, remaining)
                if qty > 0:
                    orders.append(Order(product, ask, qty))
                    remaining -= qty

        # Step 2: If we still need units, post a passive bid inside the spread
        # (bid+1 ensures we're at the front of the queue, cheaper than crossing ask)
        if remaining > 0 and od.buy_orders:
            best_bid = max(od.buy_orders)
            orders.append(Order(product, best_bid + 1, remaining))

    else:
        # ── SHORT: need to sell down to -LIMIT ───────────────────────────────
        remaining = position + LIMIT   # units we can still sell short
        if remaining <= 0:
            return orders   # already at limit

        # Step 1: Aggress the bid side — take what's available
        if od.buy_orders:
            for bid, vol in sorted(od.buy_orders.items(), reverse=True):
                if remaining <= 0:
                    break
                qty = min(vol, remaining)
                if qty > 0:
                    orders.append(Order(product, bid, -qty))
                    remaining -= qty

        # Step 2: Post passive ask inside the spread if still need units
        if remaining > 0 and od.sell_orders:
            best_ask = min(od.sell_orders)
            orders.append(Order(product, best_ask - 1, -remaining))

    return orders


# ─── Main Trader ──────────────────────────────────────────────────────────────

class Trader:
    """
    Pure momentum strategy for Round 5.
    """

    def run(self, state: TradingState) -> Tuple[Dict[str, List[Order]], int, str]:
        result: Dict[str, List[Order]] = {}

        for product, direction in MOMENTUM.items():
            if product not in state.order_depths:
                continue

            pos    = _pos(state, product)
            od     = state.order_depths[product]
            orders = momentum_orders(product, direction, pos, od)

            if orders:
                result[product] = orders

        return result, 0, ""
