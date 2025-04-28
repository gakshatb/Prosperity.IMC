from datamodel import *
from typing import List, Dict, Tuple, Any

class Logger:
    def __init__(self) -> None:
        self.logs = ""
        self.max_log_length = 3750

    def print(self, *objects: Any, sep: str = " ", end: str = "\n") -> None:
        self.logs += sep.join(map(str, objects)) + end

    def flush(self, state: TradingState, orders: dict[Symbol, list[Order]], conversions: int, trader_data: str) -> None:
        base_length = len(self.to_json([
            self.compress_state(state, ""),
            self.compress_orders(orders),
            conversions,
            "",
            "",
        ]))

        # We truncate state.traderData, trader_data, and self.logs to the same max. length to fit the log limit
        max_item_length = (self.max_log_length - base_length) // 3

        print(self.to_json([
            self.compress_state(state, self.truncate(
                state.traderData, max_item_length)),
            self.compress_orders(orders),
            conversions,
            self.truncate(trader_data, max_item_length),
            self.truncate(self.logs, max_item_length),
        ]))

        self.logs = ""

    def compress_state(self, state: TradingState, trader_data: str) -> list[Any]:
        return [
            state.timestamp,
            trader_data,
            self.compress_listings(state.listings),
            self.compress_order_depths(state.order_depths),
            self.compress_trades(state.own_trades),
            self.compress_trades(state.market_trades),
            state.position,
            self.compress_observations(state.observations),
        ]

    def compress_listings(self, listings: dict[Symbol, Listing]) -> list[list[Any]]:
        compressed = []
        for listing in listings.values():
            compressed.append(
                [listing.symbol, listing.product, listing.denomination])

        return compressed

    def compress_order_depths(self, order_depths: dict[Symbol, OrderDepth]) -> dict[Symbol, list[Any]]:
        compressed = {}
        for symbol, order_depth in order_depths.items():
            compressed[symbol] = [
                order_depth.buy_orders, order_depth.sell_orders]

        return compressed

    def compress_trades(self, trades: dict[Symbol, list[Trade]]) -> list[list[Any]]:
        compressed = []
        for arr in trades.values():
            for trade in arr:
                compressed.append([
                    trade.symbol,
                    trade.price,
                    trade.quantity,
                    trade.buyer,
                    trade.seller,
                    trade.timestamp,
                ])

        return compressed

    def compress_observations(self, observations: Observation) -> list[Any]:
        conversion_observations = {}
        for product, observation in observations.conversionObservations.items():
            conversion_observations[product] = [
                observation.bidPrice,
                observation.askPrice,
                observation.transportFees,
                observation.exportTariff,
                observation.importTariff,
                observation.sunlight,
                observation.humidity,
            ]

        return [observations.plainValueObservations, conversion_observations]

    def compress_orders(self, orders: dict[Symbol, list[Order]]) -> list[list[Any]]:
        compressed = []
        for arr in orders.values():
            for order in arr:
                compressed.append([order.symbol, order.price, order.quantity])

        return compressed

    def to_json(self, value: Any) -> str:
        return json.dumps(value, cls=ProsperityEncoder, separators=(",", ":"))

    def truncate(self, value: str, max_length: int) -> str:
        if len(value) <= max_length:
            return value

        return value[:max_length - 3] + "..."


class ResinStrategy:
    def __init__(self):
        self.product = "RAINFOREST_RESIN"
        self.limit = 50
        self.fair_price = 10000  # Assumed stable fair price

    def run(self, state, position):
        orders = []
        pos = position.get(self.product, 0)
        depth = state.order_depths[self.product]

        for price, volume in sorted(depth.sell_orders.items()):
            if price < self.fair_price and pos < self.limit:
                buy_volume = min(volume, self.limit - pos)
                orders.append(Order(self.product, price, buy_volume))
                pos += buy_volume

        for price, volume in sorted(depth.buy_orders.items(), reverse=True):
            if price > self.fair_price and pos > -self.limit:
                sell_volume = min(volume, pos + self.limit)
                orders.append(Order(self.product, price, -sell_volume))
                pos -= sell_volume

        return orders


class KelpStrategy:
    def __init__(self):
        self.product = "KELP"
        self.limit = 50
        self.prices = []
        self.window = 10

    def run(self, state, position):
        orders = []
        pos = position.get(self.product, 0)
        depth = state.order_depths[self.product]

        if depth.sell_orders and depth.buy_orders:
            mid_price = (min(depth.sell_orders.keys()) + max(depth.buy_orders.keys())) / 2
            self.prices.append(mid_price)

        if len(self.prices) > self.window:
            self.prices.pop(0)

        if len(self.prices) == self.window:
            avg_price = sum(self.prices) / self.window

            for price, volume in sorted(depth.sell_orders.items()):
                if price < avg_price * 0.98 and pos < self.limit:
                    buy_volume = min(volume, self.limit - pos)
                    orders.append(Order(self.product, price, buy_volume))
                    pos += buy_volume

            for price, volume in sorted(depth.buy_orders.items(), reverse=True):
                if price > avg_price * 1.02 and pos > -self.limit:
                    sell_volume = min(volume, pos + self.limit)
                    orders.append(Order(self.product, price, -sell_volume))
                    pos -= sell_volume

        return orders


class SquidInkStrategy:
    def __init__(self):
        self.product = "SQUID_INK"
        self.limit = 50
        self.prices = []
        self.window = 10

    def run(self, state, position):
        orders = []
        pos = position.get(self.product, 0)
        depth = state.order_depths[self.product]

        if depth.sell_orders and depth.buy_orders:
            mid_price = (min(depth.sell_orders.keys()) + max(depth.buy_orders.keys())) / 2
            self.prices.append(mid_price)

        if len(self.prices) > self.window:
            self.prices.pop(0)

        if len(self.prices) == self.window:
            avg_price = sum(self.prices) / self.window

            for price, volume in sorted(depth.sell_orders.items()):
                if price < avg_price * 0.98 and pos < self.limit:
                    buy_volume = min(volume, self.limit - pos)
                    orders.append(Order(self.product, price, buy_volume))
                    pos += buy_volume

            for price, volume in sorted(depth.buy_orders.items(), reverse=True):
                if price > avg_price * 1.02 and pos > -self.limit:
                    sell_volume = min(volume, pos + self.limit)
                    orders.append(Order(self.product, price, -sell_volume))
                    pos -= sell_volume

        return orders


class CroissantStrategy:
    def __init__(self):
        self.product = "CROISSANTS"
        self.limit = 250
        self.prices = []
        self.window = 10

    def run(self, state, position):
        orders = []
        pos = position.get(self.product, 0)
        depth = state.order_depths[self.product]

        if depth.sell_orders and depth.buy_orders:
            mid_price = (min(depth.sell_orders.keys()) + max(depth.buy_orders.keys())) / 2
            self.prices.append(mid_price)

        if len(self.prices) > self.window:
            self.prices.pop(0)

        if len(self.prices) == self.window:
            avg_price = sum(self.prices) / self.window

            for price, volume in sorted(depth.sell_orders.items()):
                if price < avg_price * 0.98 and pos < self.limit:
                    buy_volume = min(volume, self.limit - pos)
                    orders.append(Order(self.product, price, buy_volume))
                    pos += buy_volume

            for price, volume in sorted(depth.buy_orders.items(), reverse=True):
                if price > avg_price * 1.02 and pos > -self.limit:
                    sell_volume = min(volume, pos + self.limit)
                    orders.append(Order(self.product, price, -sell_volume))
                    pos -= sell_volume

        return orders


class JamStrategy:
    def __init__(self):
        self.product = "JAMS"
        self.limit = 350
        self.prices = []
        self.window = 10

    def run(self, state, position):
        orders = []
        pos = position.get(self.product, 0)
        depth = state.order_depths[self.product]

        if depth.sell_orders and depth.buy_orders:
            mid_price = (min(depth.sell_orders.keys()) + max(depth.buy_orders.keys())) / 2
            self.prices.append(mid_price)

        if len(self.prices) > self.window:
            self.prices.pop(0)

        if len(self.prices) == self.window:
            avg_price = sum(self.prices) / self.window

            for price, volume in sorted(depth.sell_orders.items()):
                if price < avg_price * 0.98 and pos < self.limit:
                    buy_volume = min(volume, self.limit - pos)
                    orders.append(Order(self.product, price, buy_volume))
                    pos += buy_volume

            for price, volume in sorted(depth.buy_orders.items(), reverse=True):
                if price > avg_price * 1.02 and pos > -self.limit:
                    sell_volume = min(volume, pos + self.limit)
                    orders.append(Order(self.product, price, -sell_volume))
                    pos -= sell_volume

        return orders


class DjembeStrategy:
    def __init__(self):
        self.product = "DJEMBES"
        self.limit = 60
        self.spread = 5

    def run(self, state, position):
        orders = []
        pos = position.get(self.product, 0)
        depth = state.order_depths[self.product]

        if depth.sell_orders and depth.buy_orders:
            best_bid = max(depth.buy_orders.keys())
            best_ask = min(depth.sell_orders.keys())
            mid_price = (best_bid + best_ask) / 2

            bid_price = int(mid_price - self.spread)
            ask_price = int(mid_price + self.spread)

            if pos < self.limit:
                orders.append(Order(self.product, bid_price, min(10, self.limit - pos)))
            if pos > -self.limit:
                orders.append(Order(self.product, ask_price, -min(10, pos + self.limit)))

        return orders


class PicnicBasketStrategy:
    def __init__(self):
        self.components = {
            "PICNIC_BASKET1": {"CROISSANTS": 6, "JAMS": 3, "DJEMBES": 1, "limit": 60},
            "PICNIC_BASKET2": {"CROISSANTS": 4, "JAMS": 2, "limit": 100},
        }

    def run(self, state, position):
        orders = []

        for basket in ["PICNIC_BASKET1", "PICNIC_BASKET2"]:
            if basket not in state.order_depths:
                continue
            depth = state.order_depths[basket]
            pos = position.get(basket, 0)
            limit = self.components[basket]["limit"]

            # Calculate estimated fair value from components
            fair_value = 0
            for component, qty in self.components[basket].items():
                if component == "limit":
                    continue
                if component in state.order_depths:
                    comp_depth = state.order_depths[component]
                    if comp_depth.sell_orders and comp_depth.buy_orders:
                        mid = (min(comp_depth.sell_orders) + max(comp_depth.buy_orders)) / 2
                        fair_value += mid * qty

            # Buy undervalued baskets
            for price, volume in sorted(depth.sell_orders.items()):
                if price < fair_value * 0.98 and pos < limit:
                    buy_volume = min(volume, limit - pos)
                    orders.append(Order(basket, price, buy_volume))
                    pos += buy_volume

            # Sell overvalued baskets
            for price, volume in sorted(depth.buy_orders.items(), reverse=True):
                if price > fair_value * 1.02 and pos > -limit:
                    sell_volume = min(volume, pos + limit)
                    orders.append(Order(basket, price, -sell_volume))
                    pos -= sell_volume

        return orders


class VolcanicRockStrategy:
    def __init__(self):
        self.product = "VOLCANIC_ROCK"
        self.limit = 400
        self.prices = []
        self.window = 15

    def run(self, state, position):
        orders = []
        pos = position.get(self.product, 0)
        depth = state.order_depths[self.product]

        if depth.buy_orders and depth.sell_orders:
            mid_price = (max(depth.buy_orders) + min(depth.sell_orders)) / 2
            self.prices.append(mid_price)

        if len(self.prices) > self.window:
            self.prices.pop(0)

        if len(self.prices) == self.window:
            avg = sum(self.prices) / self.window

            for price, volume in sorted(depth.sell_orders.items()):
                if price < avg * 0.985 and pos < self.limit:
                    buy_volume = min(volume, self.limit - pos)
                    orders.append(Order(self.product, price, buy_volume))
                    pos += buy_volume

            for price, volume in sorted(depth.buy_orders.items(), reverse=True):
                if price > avg * 1.015 and pos > -self.limit:
                    sell_volume = min(volume, pos + self.limit)
                    orders.append(Order(self.product, price, -sell_volume))
                    pos -= sell_volume

        return orders


class VoucherStrategy:
    def __init__(self):
        self.vouchers = {
            "VOLCANIC_ROCK_VOUCHER_9500": 9500,
            "VOLCANIC_ROCK_VOUCHER_9750": 9750,
            "VOLCANIC_ROCK_VOUCHER_10000": 10000,
            "VOLCANIC_ROCK_VOUCHER_10250": 10250,
            "VOLCANIC_ROCK_VOUCHER_10500": 10500
        }
        self.limit = 200

    def run(self, state, position):
        orders = []
        if "VOLCANIC_ROCK" not in state.order_depths:
            return orders

        # Estimate value of a voucher as max(VOLCANIC_ROCK price - strike, 0)
        rock_depth = state.order_depths["VOLCANIC_ROCK"]
        if not rock_depth.buy_orders or not rock_depth.sell_orders:
            return orders

        rock_mid = (max(rock_depth.buy_orders) + min(rock_depth.sell_orders)) / 2

        for voucher, strike in self.vouchers.items():
            if voucher not in state.order_depths:
                continue

            depth = state.order_depths[voucher]
            pos = position.get(voucher, 0)

            intrinsic_value = max(rock_mid - strike, 0)

            for price, volume in sorted(depth.sell_orders.items()):
                if price < intrinsic_value * 0.95 and pos < self.limit:
                    buy_volume = min(volume, self.limit - pos)
                    orders.append(Order(voucher, price, buy_volume))
                    pos += buy_volume

            for price, volume in sorted(depth.buy_orders.items(), reverse=True):
                if price > intrinsic_value * 1.05 and pos > -self.limit:
                    sell_volume = min(volume, pos + self.limit)
                    orders.append(Order(voucher, price, -sell_volume))
                    pos -= sell_volume

        return orders



class StrategyManager:
    def __init__(self):
        self.strategy_map = {}
        self.voucher_strategy = VoucherStrategy()
        self.picnic_strategy = PicnicBasketStrategy()

    def initialize_strategies(self, products_with_limits):
        for product, limit in products_with_limits.items():
            if product == "RAINFOREST_RESIN":
                self.strategy_map[product] = ResinStrategy()
            elif product == "KELP":
                self.strategy_map[product] = KelpStrategy()
            elif product == "SQUID_INK":
                self.strategy_map[product] = SquidInkStrategy()
            elif product == "CROISSANTS":
                self.strategy_map[product] = CroissantStrategy()
            elif product == "JAMS":
                self.strategy_map[product] = JamStrategy()
            elif product == "DJEMBES":
                self.strategy_map[product] = DjembeStrategy()
            elif "PICNIC_BASKET" in product:
                self.strategy_map[product] = self.picnic_strategy
            elif product == "VOLCANIC_ROCK":
                self.strategy_map[product] = VolcanicRockStrategy()
            elif "VOLCANIC_ROCK_VOUCHER" in product:
                self.strategy_map[product] = self.voucher_strategy
            else:
                print(f"[!] No strategy found for: {product}")

    def run_all(self, state, position):
        result = {}
        for product, strategy in self.strategy_map.items():
            result[product] = strategy.run(state, position)
        return result


class Trader:
    def __init__(self):
        self.logger = Logger()
        self.strategy_manager = StrategyManager()

        self.product_limits = {
            "RAINFOREST_RESIN": 50,
            "KELP": 50,
            "SQUID_INK": 50,
            "CROISSANTS": 250,
            "JAMS": 350,
            "DJEMBES": 60,
            "PICNIC_BASKET1": 60,
            "PICNIC_BASKET2": 100,
            "VOLCANIC_ROCK": 400,
            "VOLCANIC_ROCK_VOUCHER_9500": 200,
            "VOLCANIC_ROCK_VOUCHER_9750": 200,
            "VOLCANIC_ROCK_VOUCHER_10000": 200,
            "VOLCANIC_ROCK_VOUCHER_10250": 200,
            "VOLCANIC_ROCK_VOUCHER_10500": 200
        }

        self.strategy_manager.initialize_strategies(self.product_limits)

    def run(self, state: TradingState) -> Tuple[Dict[str, List[Order]], int, str]:
        trader_data = "SAMPLE"
        conversions = 1

        self.logger.print("Trader Data:", state.traderData)
        self.logger.print("Observations:", state.observations)

        try:
            all_orders = self.strategy_manager.run_all(state, state.position)
            self.logger.print("Generated Orders:", all_orders)
        except Exception as e:
            self.logger.print("Strategy Manager Error:", str(e))
            all_orders = {}

        # Flush logs (print final output as JSON for backend logging)
        self.logger.flush(state, all_orders, conversions, trader_data)

        return all_orders, conversions, trader_data