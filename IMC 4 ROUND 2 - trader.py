from datamodel import OrderDepth, UserId, TradingState, Order
from typing import List
import json
import math

class Trader:
    """
    Round 2 — v9
    """
    POSITION_LIMIT = {
        "ASH_COATED_OSMIUM": 80,
        "INTARIAN_PEPPER_ROOT": 80,
    }

    ACO_FAIR_VALUE = 10000

    def bid(self) -> int:
        """
        """
        return 1500

    def run(self, state: TradingState):
        result = {}
        conversions = 0
        try:
            saved = json.loads(state.traderData) if state.traderData else {}
        except Exception:
            saved = {}
        if "ASH_COATED_OSMIUM" in state.order_depths:
            result["ASH_COATED_OSMIUM"] = self.trade_aco(state, saved)
        if "INTARIAN_PEPPER_ROOT" in state.order_depths:
            result["INTARIAN_PEPPER_ROOT"] = self.trade_ipr(state, saved)

        return result, conversions, json.dumps(saved)

    def _is_auction(self, state: TradingState) -> bool:
        return state.timestamp == 0

    def trade_aco(self, state: TradingState, saved: dict) -> List[Order]:
        orders = []
        product = "ASH_COATED_OSMIUM"
        od: OrderDepth = state.order_depths[product]
        pos = state.position.get(product, 0)
        limit = self.POSITION_LIMIT[product]
        fair = self.ACO_FAIR_VALUE

        if self._is_auction(state):
            return orders

        inventory_skew = pos / limit
        skew = round(inventory_skew * 2)

        bid_offset = 3 + max(0, skew)
        ask_offset = 3 + max(0, -skew)
        
        our_bid = fair - bid_offset
        our_ask = fair + ask_offset

        bid_size = min(12, limit - pos)
        ask_size = min(12, limit + pos)

        if bid_size > 0:
            orders.append(Order(product, our_bid, bid_size))
        if ask_size > 0:
            orders.append(Order(product, our_ask, -ask_size))

        return orders

    def trade_ipr(self, state: TradingState, saved: dict) -> List[Order]:
        orders = []
        product = "INTARIAN_PEPPER_ROOT"
        od: OrderDepth = state.order_depths[product]
        pos = state.position.get(product, 0)
        limit = self.POSITION_LIMIT[product]
        ts = state.timestamp

        best_bid = max(od.buy_orders.keys()) if od.buy_orders else None
        best_ask = min(od.sell_orders.keys()) if od.sell_orders else None

        if best_bid and best_ask:
            observed_mid = (best_bid + best_ask) / 2
            raw_base = observed_mid - ts * 0.001
            if "ipr_base" not in saved:
                saved["ipr_base"] = round(raw_base / 1000) * 1000
                saved["ipr_base_n"] = 1
            else:
                n = saved.get("ipr_base_n", 20)
                alpha = 1.0 / (n + 1) if n < 20 else 0.02
                saved["ipr_base_n"] = min(n + 1, 20)
                saved["ipr_base"] = (1 - alpha) * saved["ipr_base"] + alpha * raw_base

        base = saved.get("ipr_base", 13000)
        fair = base + ts * 0.001

        if self._is_auction(state):
            auction_price = int(best_ask) + 3 if best_ask else int(fair) + 10
            qty = min(80, limit - pos)
            if qty > 0:
                orders.append(Order(product, auction_price, qty))
            return orders

        if od.sell_orders and pos < limit:
            for ask in sorted(od.sell_orders.keys()):
                if ask <= fair - 5:
                    qty = min(-od.sell_orders[ask], limit - pos)
                    if qty > 0:
                        orders.append(Order(product, ask, qty))
                        pos += qty

        if pos < limit:
            bid_size = min(8, limit - pos)
            if bid_size > 0:
                orders.append(Order(product, math.floor(fair) - 4, bid_size))

        return orders