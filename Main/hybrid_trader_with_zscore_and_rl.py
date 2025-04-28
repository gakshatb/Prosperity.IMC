
from datamodel import OrderDepth, TradingState, Order
from typing import List, Dict
import numpy as np

class Trader:
    
    def __init__(self):
        self.price_history = {}  # Store price history per product
        self.alpha = 0.2  # EMA smoothing factor
        self.var_confidence = 0.95  # Confidence level for VaR-based stop-loss
        
        # Placeholder for Reinforcement Learning model (can integrate later)
        self.rl_model = None

    def compute_ema(self, prices, window):
        if len(prices) < window:
            return np.mean(prices)
        ema = prices[0]
        for price in prices[1:]:
            ema = (self.alpha * price) + ((1 - self.alpha) * ema)
        return ema

    def compute_bollinger_bands(self, prices, window=20):
        if len(prices) < window:
            return None, None
        mean = np.mean(prices[-window:])
        std_dev = np.std(prices[-window:])
        upper_band = mean + (2 * std_dev)
        lower_band = mean - (2 * std_dev)
        return upper_band, lower_band

    def compute_volatility(self, prices, window=10):
        if len(prices) < window:
            return np.std(prices) if len(prices) > 1 else 0
        return np.std(prices[-window:])

    def compute_var(self, prices):
        if len(prices) < 2:
            return 0
        returns = np.diff(prices) / np.array(prices[:-1])
        return abs(np.percentile(returns, (1 - self.var_confidence) * 100))

    def compute_z_score(self, prices, window=20):
        if len(prices) < window:
            return 0
        mean = np.mean(prices[-window:])
        std = np.std(prices[-window:])
        if std == 0:
            return 0
        return (prices[-1] - mean) / std

    def run(self, state: TradingState):
        result = {}
        position_limits = {"RAINFOREST_RESIN": 50, "KELP": 50, "SQUID_INK": 50}
        current_positions = state.position

        for product in state.order_depths:
            order_depth: OrderDepth = state.order_depths[product]
            orders: List[Order] = []

            if not order_depth.buy_orders or not order_depth.sell_orders:
                continue

            best_bid = max(order_depth.buy_orders.keys())
            best_ask = min(order_depth.sell_orders.keys())
            mid_price = (best_bid + best_ask) / 2
            spread = best_ask - best_bid

            # Store history
            if product not in self.price_history:
                self.price_history[product] = []
            self.price_history[product].append(mid_price)

            # Position sizing
            volatility = self.compute_volatility(self.price_history[product])
            var = self.compute_var(self.price_history[product])
            base_size = 10
            trade_size = max(1, int(base_size * (1 - var)))

            pos = current_positions.get(product, 0)
            limit = position_limits[product]

            if product == "RAINFOREST_RESIN":
                fair_price = mid_price  # Assume mean reverting stable
                buy_price = fair_price - 1
                sell_price = fair_price + 1
                if pos < limit:
                    orders.append(Order(product, buy_price, min(trade_size, limit - pos)))
                if pos > -limit:
                    orders.append(Order(product, sell_price, -min(trade_size, pos + limit)))

            elif product == "KELP":
                short_ema = self.compute_ema(self.price_history[product], 5)
                long_ema = self.compute_ema(self.price_history[product], 20)
                upper_band, lower_band = self.compute_bollinger_bands(self.price_history[product])
                momentum = short_ema - long_ema

                if self.rl_model:
                    action = self.rl_model.predict(state=state)
                    if action == "BUY" and pos < limit:
                        orders.append(Order(product, best_ask, min(trade_size, limit - pos)))
                    elif action == "SELL" and pos > -limit:
                        orders.append(Order(product, best_bid, -min(trade_size, pos + limit)))
                else:
                    if mid_price < lower_band and pos < limit:
                        orders.append(Order(product, best_ask, min(trade_size, limit - pos)))
                    if mid_price > upper_band and pos > -limit:
                        orders.append(Order(product, best_bid, -min(trade_size, pos + limit)))

            elif product == "SQUID_INK":
                z_score = self.compute_z_score(self.price_history[product])
                if z_score < -1.5 and pos < limit:
                    orders.append(Order(product, best_ask, min(trade_size, limit - pos)))
                elif z_score > 1.5 and pos > -limit:
                    orders.append(Order(product, best_bid, -min(trade_size, pos + limit)))

            result[product] = orders

        return result, 0, "Hybrid Strategy w/ RL & Z-Score Reversion"
