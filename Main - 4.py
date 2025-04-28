from datamodel import OrderDepth, TradingState, Order
from typing import List, Dict
import statistics

POSITION_LIMITS = {
    "RAINFOREST_RESIN": 50,
    "KELP": 50,
    "SQUID_INK": 50,
    "CROISSANTS": 250,
    "JAM": 350,
    "DJEMBE": 60,
    "PICNIC_BASKET_1": 60,
    "PICNIC_BASKET_2": 100,
    "VOLCANIC_ROCK": 20,
    "MAGNIFICENT_MACARON": 75
}

CONVERSION_LIMITS = {
    "MAGNIFICENT_MACARON": 10
}

class BaseStrategy:
    def __init__(self, product: str):
        self.product = product
        self.position = 0
        self.fair_value = 0
        self.window = []

    def update_position(self, state: TradingState):
        self.position = state.position.get(self.product, 0)

    def calculate_fair_value(self, order_depth: OrderDepth):
        all_prices = list(order_depth.buy_orders.keys()) + list(order_depth.sell_orders.keys())
        if all_prices:
            mid_price = (max(order_depth.buy_orders.keys()) + min(order_depth.sell_orders.keys())) / 2
            self.window.append(mid_price)
            if len(self.window) > 20:
                self.window.pop(0)
            self.fair_value = statistics.mean(self.window)
        else:
            self.fair_value = 0

    def run(self, state: TradingState) -> List[Order]:
        return []

class SimpleMeanReversionStrategy(BaseStrategy):
    def run(self, state: TradingState) -> List[Order]:
        self.update_position(state)
        order_depth = state.order_depths[self.product]
        self.calculate_fair_value(order_depth)
        orders = []

        spread = 1  # Base spread
        available_buy = POSITION_LIMITS[self.product] - self.position
        available_sell = self.position + POSITION_LIMITS[self.product]

        for ask, ask_vol in sorted(order_depth.sell_orders.items()):
            if ask < self.fair_value - spread and available_buy > 0:
                volume = min(-ask_vol, available_buy)
                orders.append(Order(self.product, ask, volume))
                available_buy -= volume

        for bid, bid_vol in sorted(order_depth.buy_orders.items(), reverse=True):
            if bid > self.fair_value + spread and available_sell > 0:
                volume = min(bid_vol, available_sell)
                orders.append(Order(self.product, bid, -volume))
                available_sell -= volume

        return orders

class BasketStrategy(BaseStrategy):
    def __init__(self, product: str, components: Dict[str, int]):
        super().__init__(product)
        self.components = components

    def run(self, state: TradingState) -> List[Order]:
        self.update_position(state)
        order_depth = state.order_depths[self.product]
        component_value = 0
        total_count = 0

        for comp, qty in self.components.items():
            if comp in state.order_depths:
                od = state.order_depths[comp]
                bid = max(od.buy_orders) if od.buy_orders else 0
                ask = min(od.sell_orders) if od.sell_orders else 0
                fair = (bid + ask) / 2 if bid and ask else 0
                component_value += fair * qty
                total_count += qty

        self.fair_value = component_value / total_count if total_count else 0
        spread = 1
        orders = []

        available_buy = POSITION_LIMITS[self.product] - self.position
        available_sell = self.position + POSITION_LIMITS[self.product]

        for ask, ask_vol in sorted(order_depth.sell_orders.items()):
            if ask < self.fair_value - spread and available_buy > 0:
                volume = min(-ask_vol, available_buy)
                orders.append(Order(self.product, ask, volume))
                available_buy -= volume

        for bid, bid_vol in sorted(order_depth.buy_orders.items(), reverse=True):
            if bid > self.fair_value + spread and available_sell > 0:
                volume = min(bid_vol, available_sell)
                orders.append(Order(self.product, bid, -volume))
                available_sell -= volume

        return orders

class MacaronStrategy(BaseStrategy):
    def run(self, state: TradingState) -> List[Order]:
        self.update_position(state)
        order_depth = state.order_depths[self.product]
        self.calculate_fair_value(order_depth)
        orders = []

        tariff = 2  # Example tariff
        transport_fee = 1
        storage_cost = 0.5
        spread = tariff + transport_fee + storage_cost

        available_buy = POSITION_LIMITS[self.product] - self.position
        available_sell = self.position + POSITION_LIMITS[self.product]

        for ask, ask_vol in sorted(order_depth.sell_orders.items()):
            if ask < self.fair_value - spread and available_buy > 0:
                volume = min(-ask_vol, available_buy)
                orders.append(Order(self.product, ask, volume))
                available_buy -= volume

        for bid, bid_vol in sorted(order_depth.buy_orders.items(), reverse=True):
            if bid > self.fair_value + spread and available_sell > 0:
                volume = min(bid_vol, available_sell)
                orders.append(Order(self.product, bid, -volume))
                available_sell -= volume

        return orders

class Trader:
    def __init__(self):
        self.strategies = {
            "RAINFOREST_RESIN": SimpleMeanReversionStrategy("RAINFOREST_RESIN"),
            "KELP": SimpleMeanReversionStrategy("KELP"),
            "SQUID_INK": SimpleMeanReversionStrategy("SQUID_INK"),
            "CROISSANTS": SimpleMeanReversionStrategy("CROISSANTS"),
            "JAM": SimpleMeanReversionStrategy("JAM"),
            "DJEMBE": SimpleMeanReversionStrategy("DJEMBE"),
            "PICNIC_BASKET_1": BasketStrategy("PICNIC_BASKET_1", {
                "CROISSANTS": 6, "JAM": 3, "DJEMBE": 1
            }),
            "PICNIC_BASKET_2": BasketStrategy("PICNIC_BASKET_2", {
                "CROISSANTS": 4, "JAM": 2
            }),
            "VOLCANIC_ROCK": SimpleMeanReversionStrategy("VOLCANIC_ROCK"),
            "MAGNIFICENT_MACARON": MacaronStrategy("MAGNIFICENT_MACARON")
        }

    def run(self, state: TradingState) -> Dict[str, List[Order]]:
        result = {}
        for product in state.order_depths:
            if product in self.strategies:
                result[product] = self.strategies[product].run(state)
        return result
