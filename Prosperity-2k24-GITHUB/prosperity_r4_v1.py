from datamodel import Listing, Observation, Order, OrderDepth, ProsperityEncoder, Symbol, Trade, TradingState
from typing import List, Any, Dict, Tuple
import string
import json
import collections
from collections import defaultdict
import copy
import numpy as np
from statistics import NormalDist
from statistics import mean as statmean

#NormalDist(mu=0, sigma=1).cdf(1.96)

empty_dict = {'STARFRUIT' : 0, 'AMETHYSTS' : 0, 'ORCHIDS' : 0, 'CHOCOLATE': 0, 'STRAWBERRIES': 0, 'ROSES' : 0, 'GIFT_BASKET': 0, 'COCONUT_COUPON': 0, 'COCONUT': 0}
def def_value():
    return copy.deepcopy(empty_dict)

INF = int(1e9)

class Logger:
    def __init__(self) -> None:
        self.logs = ""
        self.max_log_length = 3750

    def print(self, *objects: Any, sep: str = " ", end: str = "\n") -> None:
        self.logs += sep.join(map(str, objects)) + end

    def flush(self, state: TradingState, orders: Dict[Symbol, List[Order]], conversions: int, trader_data: str) -> None:
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
            self.compress_state(state, self.truncate(state.traderData, max_item_length)),
            self.compress_orders(orders),
            conversions,
            self.truncate(trader_data, max_item_length),
            self.truncate(self.logs, max_item_length),
        ]))

        self.logs = ""

    def compress_state(self, state: TradingState, trader_data: str) -> List[Any]:
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

    def compress_listings(self, listings: Dict[Symbol, Listing]) -> List[List[Any]]:
        compressed = []
        for listing in listings.values():
            compressed.append([listing["symbol"], listing["product"], listing["denomination"]])

        return compressed

    def compress_order_depths(self, order_depths: Dict[Symbol, OrderDepth]) -> Dict[Symbol, List[Any]]:
        compressed = {}
        for symbol, order_depth in order_depths.items():
            compressed[symbol] = [order_depth.buy_orders, order_depth.sell_orders]

        return compressed

    def compress_trades(self, trades: Dict[Symbol, List[Trade]]) -> List[List[Any]]:
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

    def compress_observations(self, observations: Observation) -> List[Any]:
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

    def compress_orders(self, orders: Dict[Symbol, List[Order]]) -> List[List[Any]]:
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

logger = Logger()

def normCDf(x):
    return NormalDist().cdf(x)

class Trader:
    POSITION_LIMIT = {'STARFRUIT' : 20, 'AMETHYSTS' : 20, 'ORCHIDS': 100, 'CHOCOLATE': 250, 'STRAWBERRIES': 350, 'ROSES' : 60, 'GIFT_BASKET': 60, 'COCONUT_COUPON': 600, 'COCONUT': 300}
    position = copy.deepcopy(empty_dict)
    volume_traded = copy.deepcopy(empty_dict)

    person_position = defaultdict(def_value)
    person_actvalof_position = defaultdict(def_value)

    basket_types = ['CHOCOLATE', 'STRAWBERRIES', 'ROSES', 'GIFT_BASKET']
    basket_std = 117

    productCache = {'STARFRUIT' : [], 'AMETHYSTS' : [], 'ORCHIDS': []}
    productDim = {'STARFRUIT' : 4, 'AMETHYSTS' : 4, 'ORCHIDS': 4}
    person_position = defaultdict(def_value)

    cont_buy_basket_unfill = 0
    cont_sell_basket_unfill = 0

    cpnl = defaultdict(lambda : 0)
    coconut_strike = 10000
    coupon_price = 637.63
    coupon_implied_vol = 0.195

    @staticmethod
    def normCDf(x):
        return NormalDist().cdf(x)
    
    def bs_logic(self, product, order_depth):
        orders: List[Order] = []
        #acceptable_price = 9.8  # Participant should calculate this value

        avg_price = 0
        sum_buy_price = 0
        total_buy_units = 0
        sum_sell_price = 0
        total_sell_units = 0

        for key, value in order_depth.buy_orders.items():
            sum_buy_price += (key*value)
            total_buy_units += value

        for key, value in order_depth.sell_orders.items():
            sum_sell_price -= (key*value)
            total_sell_units -= value

        avg_buy_price  = sum_buy_price/total_buy_units
        avg_sell_price = sum_sell_price/total_sell_units
        avg_price = (sum_buy_price + sum_sell_price)/(total_buy_units + total_sell_units)

        logger.print("average buy price", avg_buy_price)
        logger.print("average sell price", avg_sell_price)
        co_eff = 1.01
        if product == 'AMETHYSTS':
            co_eff = 1.05

        acceptable_price_buy = avg_sell_price*co_eff
        acceptable_price_sell = avg_buy_price*co_eff
        #logger.print("Acceptable price : " + str(acceptable_price))
        logger.print("Buy Order depth : " + str(len(order_depth.buy_orders)) + ", Sell order depth : " + str(len(order_depth.sell_orders)))

        if len(order_depth.sell_orders) != 0:
            best_ask, best_ask_amount = list(order_depth.sell_orders.items())[0]
            logger.print("Best sell ask", str(best_ask_amount) + "x", best_ask)
            if int(best_ask) <= acceptable_price_buy:
                logger.print("BUY", str(-best_ask_amount) + "x", best_ask)
                orders.append(Order(product, best_ask, -best_ask_amount))

        if len(order_depth.buy_orders) != 0:
            best_bid, best_bid_amount = list(order_depth.buy_orders.items())[0]
            logger.print("Best buy bid", str(best_bid_amount) + "x", best_bid)
            if int(best_bid) >= acceptable_price_sell:
                logger.print("SELL", str(best_bid_amount) + "x", best_bid)
                orders.append(Order(product, best_bid, -best_bid_amount))   
                
        return orders

    @staticmethod
    def BS_CALL(S, K, T, r, sigma):
        d1 = (np.log(S/K) + (r + sigma**2/2)*T) / (sigma*np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)
        return S * (normCDf(d1)) - K * np.exp(-r*T)* (normCDf(d2))

    @staticmethod
    def BS_PUT(S, K, T, r, sigma):
        d1 = (np.log(S/K) + (r + sigma**2/2)*T) / (sigma*np.sqrt(T))
        d2 = d1 - sigma* np.sqrt(T)
        return K*np.exp(-r*T)*(normCDf(-d2)) - S* (normCDf(-d1))

    def black_scholes_price(self, marketPrice):
        return self.BS_CALL(marketPrice, self.coconut_strike, (246/365), 0.00, self.coupon_implied_vol)


    def compute_orders_coupons(self, order_depth):
        orders = {'COCONUT_COUPON' : [], 'COCONUT':[]}
        osell, obuy, best_sell, best_buy, worst_sell, worst_buy, mid_price, vol_buy, vol_sell = {}, {}, {}, {}, {}, {}, {}, {}, {}
        prods = ['COCONUT_COUPON', 'COCONUT']

        for p in prods:
            osell[p] = collections.OrderedDict(sorted(order_depth[p].sell_orders.items()))
            obuy[p] = collections.OrderedDict(sorted(order_depth[p].buy_orders.items(), reverse=True))

            if len(osell[p]):
                best_sell[p] = next(iter(osell[p]))
            else:
                best_sell[p] = 20000

            if len(obuy[p]):
                best_buy[p] = next(iter(obuy[p]))
            else:
                best_buy[p] = 10

            if len(osell[p]):
                worst_sell[p] = next(reversed(osell[p]))
            else:
                worst_sell[p] = 20000                

            if len(obuy[p]):
                worst_buy[p] = next(reversed(obuy[p]))
            else:
                worst_buy[p] = 10

            print("product: ", p)
            print("best_buy: ")
            print(best_buy[p])
            print("worst_buy: ")
            print(worst_buy[p])

            print("best_sell: ")
            print(best_sell[p])
            print("worst_sell: ")
            print(worst_sell[p])


            mid_price[p] = statmean([best_sell[p], best_buy[p]])
            vol_buy[p], vol_sell[p] = 0, 0
            for price, vol in obuy[p].items():
                vol_buy[p] += vol 
                if vol_buy[p] >= self.POSITION_LIMIT[p]/10:
                    break
            for price, vol in osell[p].items():
                vol_sell[p] += -vol 
                if vol_sell[p] >= self.POSITION_LIMIT[p]/10:
                    break



        acceptable_coupon_price = self.black_scholes_price(mid_price['COCONUT']*2.5 - 15000)
        print("acceptable_coupon_price", acceptable_coupon_price)

        if(best_sell['COCONUT_COUPON'] < acceptable_coupon_price):
            vol = min(self.POSITION_LIMIT['COCONUT_COUPON'] - self.position['COCONUT_COUPON'], order_depth['COCONUT_COUPON'].sell_orders[best_sell['COCONUT_COUPON']])
            orders['COCONUT_COUPON'].append(Order('COCONUT_COUPON', best_sell['COCONUT_COUPON'], vol))

        if(worst_buy['COCONUT_COUPON'] > acceptable_coupon_price):
            vol1 = max(-self.POSITION_LIMIT['COCONUT_COUPON'] - self.position['COCONUT_COUPON'], order_depth['COCONUT_COUPON'].buy_orders[worst_buy['COCONUT_COUPON']])
            orders['COCONUT_COUPON'].append(Order('COCONUT_COUPON', best_sell['COCONUT_COUPON'], vol1))

        return orders


    def compute_orders_basket(self, order_depth):

        orders = {'STRAWBERRIES' : [], 'CHOCOLATE': [], 'ROSES' : [], 'GIFT_BASKET' : []}
        prods = self.basket_types
        osell, obuy, best_sell, best_buy, worst_sell, worst_buy, mid_price, vol_buy, vol_sell = {}, {}, {}, {}, {}, {}, {}, {}, {}

        for p in prods:
            osell[p] = collections.OrderedDict(sorted(order_depth[p].sell_orders.items()))
            obuy[p] = collections.OrderedDict(sorted(order_depth[p].buy_orders.items(), reverse=True))

            best_sell[p] = next(iter(osell[p]))
            best_buy[p] = next(iter(obuy[p]))

            worst_sell[p] = next(reversed(osell[p]))
            worst_buy[p] = next(reversed(obuy[p]))

            mid_price[p] = (best_sell[p] + best_buy[p])/2
            vol_buy[p], vol_sell[p] = 0, 0
            for price, vol in obuy[p].items():
                vol_buy[p] += vol 
                if vol_buy[p] >= self.POSITION_LIMIT[p]/10:
                    break
            for price, vol in osell[p].items():
                vol_sell[p] += -vol 
                if vol_sell[p] >= self.POSITION_LIMIT[p]/10:
                    break

        res_buy = mid_price['GIFT_BASKET'] - mid_price['STRAWBERRIES']*6 - mid_price['CHOCOLATE']*4 - mid_price['ROSES'] - 375
        res_sell = mid_price['GIFT_BASKET'] - mid_price['STRAWBERRIES']*6 - mid_price['CHOCOLATE']*4 - mid_price['ROSES'] - 375

        trade_at = self.basket_std*0.5
        close_at = self.basket_std*(-10)

        pb_pos = self.position['GIFT_BASKET']
        pb_neg = self.position['GIFT_BASKET']

        #roses_positive = self.position['ROSES']
        #roses_negative = self.position['ROSES']


        basket_buy_sig = 0
        basket_sell_sig = 0

        if self.position['GIFT_BASKET'] == self.POSITION_LIMIT['GIFT_BASKET']:
            self.cont_buy_basket_unfill = 0
        if self.position['GIFT_BASKET'] == -self.POSITION_LIMIT['GIFT_BASKET']:
            self.cont_sell_basket_unfill = 0

        do_bask = 0

        if res_sell > trade_at:
            vol = self.position['GIFT_BASKET'] + self.POSITION_LIMIT['GIFT_BASKET']
            self.cont_buy_basket_unfill = 0 # no need to buy rn
            assert(vol >= 0)
            if vol > 0:
                do_bask = 1
                basket_sell_sig = 1
                orders['GIFT_BASKET'].append(Order('GIFT_BASKET', worst_buy['GIFT_BASKET'], -vol)) 
                self.cont_sell_basket_unfill += 2
                pb_neg -= vol
        elif res_buy < close_at:
            vol = self.POSITION_LIMIT['GIFT_BASKET'] - self.position['GIFT_BASKET']
            self.cont_sell_basket_unfill = 0 # no need to sell rn
            assert(vol >= 0)
            if vol > 0:
                do_bask = 1
                basket_buy_sig = 1
                orders['GIFT_BASKET'].append(Order('GIFT_BASKET', worst_sell['GIFT_BASKET'], vol))
                self.cont_buy_basket_unfill += 2
                pb_pos += vol

        return orders

    def calc_next_price_product(self, product):
        # starfruits cache stores price from 1 day ago, current day resp
        # by price, here we mean mid price

        coef = [-0.01869561,  0.0455032 ,  0.16316049,  0.8090892]
        intercept = 4.481696494462085
        nxt_price = intercept
        for i, val in enumerate(self.productCache[product]):
            nxt_price += val * coef[i]

        return int(round(nxt_price))

    def values_extract(self, order_dict, buy=0):
        tot_vol = 0
        best_val = -1
        mxvol = -1

        for ask, vol in order_dict.items():
            if(buy==0):
                vol *= -1
            tot_vol += vol
            if tot_vol > mxvol:
                mxvol = vol
                best_val = ask
        
        return tot_vol, best_val

    def compute_orders_regression(self, product, order_depth, acc_bid, acc_ask, LIMIT):
        orders: list[Order] = []

        osell = collections.OrderedDict(sorted(order_depth.sell_orders.items()))
        obuy = collections.OrderedDict(sorted(order_depth.buy_orders.items(), reverse=True))

        sell_vol, best_sell_pr = self.values_extract(osell)
        buy_vol, best_buy_pr = self.values_extract(obuy, 1)

        cpos = self.position[product]

        for ask, vol in osell.items():
            if ((ask <= acc_bid) or ((self.position[product]<0) and (ask == acc_bid+1))) and cpos < LIMIT:
                order_for = min(-vol, LIMIT - cpos)
                cpos += order_for
                assert(order_for >= 0)
                orders.append(Order(product, ask, order_for))

        undercut_buy = best_buy_pr + 1
        undercut_sell = best_sell_pr - 1

        bid_pr = min(undercut_buy, acc_bid) # we will shift this by 1 to beat this price
        sell_pr = max(undercut_sell, acc_ask)

        if cpos < LIMIT:
            num = LIMIT - cpos
            orders.append(Order(product, bid_pr, num))
            cpos += num
        
        cpos = self.position[product]
        

        for bid, vol in obuy.items():
            if ((bid >= acc_ask) or ((self.position[product]>0) and (bid+1 == acc_ask))) and cpos > -LIMIT:
                order_for = max(-vol, -LIMIT-cpos)
                # order_for is a negative number denoting how much we will sell
                cpos += order_for
                assert(order_for <= 0)
                orders.append(Order(product, bid, order_for))

        if cpos > -LIMIT:
            num = -LIMIT-cpos
            orders.append(Order(product, sell_pr, num))
            cpos += num

        return orders

    def compute_orders_amethysts(self, product : str, order_depth : OrderDepth, acc_bid: int, acc_ask: int) -> List[Order]:
        orders: list[Order] = []

        osell = collections.OrderedDict(sorted(order_depth.sell_orders.items()))
        obuy = collections.OrderedDict(sorted(order_depth.buy_orders.items(), reverse=True))

        sell_vol, best_sell_pr = self.values_extract(osell)
        buy_vol, best_buy_pr = self.values_extract(obuy, 1)

        cpos = self.position[product]

        mx_with_buy = -1

        for ask, vol in osell.items():
            if ((ask < acc_bid) or ((self.position[product]<0) and (ask == acc_bid))) and cpos < self.POSITION_LIMIT['AMETHYSTS']:
                mx_with_buy = max(mx_with_buy, ask)
                order_for = min(-vol, self.POSITION_LIMIT['AMETHYSTS'] - cpos)
                cpos += order_for
                assert(order_for >= 0)
                orders.append(Order(product, ask, order_for))

        mprice_actual = (best_sell_pr + best_buy_pr)/2
        mprice_ours = (acc_bid+acc_ask)/2

        undercut_buy = best_buy_pr + 1
        undercut_sell = best_sell_pr - 1

        bid_pr = min(undercut_buy, acc_bid-1) # we will shift this by 1 to beat this price
        sell_pr = max(undercut_sell, acc_ask+1)

        if (cpos < self.POSITION_LIMIT['AMETHYSTS']) and (self.position[product] < 0):
            num = min(40, self.POSITION_LIMIT['AMETHYSTS'] - cpos)
            orders.append(Order(product, min(undercut_buy + 1, acc_bid-1), num))
            cpos += num

        if (cpos < self.POSITION_LIMIT['AMETHYSTS']) and (self.position[product] > 15):
            num = min(40, self.POSITION_LIMIT['AMETHYSTS'] - cpos)
            orders.append(Order(product, min(undercut_buy - 1, acc_bid-1), num))
            cpos += num

        if cpos < self.POSITION_LIMIT['AMETHYSTS']:
            num = min(40, self.POSITION_LIMIT['AMETHYSTS'] - cpos)
            orders.append(Order(product, bid_pr, num))
            cpos += num
        
        cpos = self.position[product]

        for bid, vol in obuy.items():
            if ((bid > acc_ask) or ((self.position[product] > 0) and (bid == acc_ask))) and cpos > -self.POSITION_LIMIT['AMETHYSTS']:
                order_for = max(-vol, -self.POSITION_LIMIT['AMETHYSTS']-cpos)
                # order_for is a negative number denoting how much we will sell
                cpos += order_for
                assert(order_for <= 0)
                orders.append(Order(product, bid, order_for))

        if (cpos > -self.POSITION_LIMIT['AMETHYSTS']) and (self.position[product] > 0):
            num = max(-40, -self.POSITION_LIMIT['AMETHYSTS']-cpos)
            orders.append(Order(product, max(undercut_sell-1, acc_ask+1), num))
            cpos += num

        if (cpos > -self.POSITION_LIMIT['AMETHYSTS']) and (self.position[product] < -15):
            num = max(-40, -self.POSITION_LIMIT['AMETHYSTS']-cpos)
            orders.append(Order(product, max(undercut_sell+1, acc_ask+1), num))
            cpos += num

        if cpos > -self.POSITION_LIMIT['AMETHYSTS']:
            num = max(-40, -self.POSITION_LIMIT['AMETHYSTS']-cpos)
            orders.append(Order(product, sell_pr, num))
            cpos += num

        return orders

    
    def run(self, state: TradingState)-> Tuple[Dict[Symbol, List[Order]], int, str]:
        #logger.print("traderData: " + state.traderData)
        #logger.print("Observations: " + str(state.observations))
        #print(type(state.observations))

        # Orders to be placed on exchange matching engine
        result = {'STARFRUIT':[], 'AMETHYSTS':[], 'ORCHIDS':[], 'CHOCOLATE': [], 'STRAWBERRIES': [], 'ROSES' : [], 'GIFT_BASKET': [], 'COCONUT' :[], 'COCONUT_COUPON' : []}

        reg_prod_list = ['STARFRUIT'] # , 'ORCHIDS'
        is_orchids = False
        is_basket = True

        if is_orchids:
            reg_prod_list.append('ORCHIDS')

        pearls_lb = 10000
        pearls_ub = 10000


        for product in reg_prod_list:

            if len(self.productCache[product]) == self.productDim[product]:
                self.productCache[product].pop(0)

        for product in reg_prod_list:
            bs, bb = 0, 0
            if product in state.order_depths:
                _, bs = self.values_extract(collections.OrderedDict(sorted(state.order_depths[product].sell_orders.items())))
                _, bb = self.values_extract(collections.OrderedDict(sorted(state.order_depths[product].buy_orders.items(), reverse=True)), 1)

            self.productCache[product].append((bs+bb)/2)

        for key, val in state.position.items():
            self.position[key] = val

        starfruits_lb, orchids_lb = -INF, -INF
        starfruits_ub, orchids_ub = INF, INF


        if len(self.productCache['STARFRUIT']) == self.productDim['STARFRUIT']:
            starfruits_lb = self.calc_next_price_product('STARFRUIT')-1
            starfruits_ub = self.calc_next_price_product('STARFRUIT')+1

        if is_orchids:

            if len(self.productCache['ORCHIDS']) == self.productDim['ORCHIDS']:
                transportFee = state.observations.conversionObservations["ORCHIDS"].transportFees
                exportTariff = state.observations.conversionObservations["ORCHIDS"].exportTariff
                importTariff = state.observations.conversionObservations["ORCHIDS"].importTariff
                orchids_lb = self.calc_next_price_product('ORCHIDS') - 1 + transportFee + importTariff
                orchids_ub = self.calc_next_price_product('ORCHIDS') + 1 + transportFee + exportTariff

        for product, order_depth in state.order_depths.items():
            #order_depth: OrderDepth = state.order_depths[product]
            orders = []
            if product == 'STARFRUIT':
                #orders = self.bs_logic(product, order_depth)
                orders = self.compute_orders_regression(product, order_depth, starfruits_lb, starfruits_ub, self.POSITION_LIMIT[product])
            elif product == 'AMETHYSTS':
                orders = self.compute_orders_amethysts(product, order_depth, pearls_lb, pearls_ub)
            elif is_orchids and product == 'ORCHIDS':
                orders = self.compute_orders_regression(product, order_depth, orchids_lb, orchids_ub, self.POSITION_LIMIT[product])
            result[product] = orders

            if is_basket and (product in self.basket_types):
                order_basket = self.compute_orders_basket(state.order_depths)
                for prd in self.basket_types:
                    result[prd] += order_basket[prd]

        is_coupon = False 
        if is_coupon:
            order_coupon = self.compute_orders_coupons(state.order_depths)
            for prd in ['COCONUT', 'COCONUT_COUPON']:
                result[prd] += order_coupon[prd]

        timestamp = state.timestamp

        for product in state.own_trades.keys():
            for trade in state.own_trades[product]:
                if trade.timestamp != state.timestamp-100:
                    continue
                #logger.print(f'We are trading {product}, {trade.buyer}, {trade.seller}, {trade.quantity}, {trade.price}')
                self.volume_traded[product] += abs(trade.quantity)
                if trade.buyer == "SUBMISSION":
                    self.cpnl[product] -= trade.quantity * trade.price
                else:
                    self.cpnl[product] += trade.quantity * trade.price

        totpnl = 0

        for product in state.order_depths.keys():
            settled_pnl = 0
            best_sell = 0 if len(state.order_depths[product].sell_orders.keys()) == 0 else min(state.order_depths[product].sell_orders.keys())
            best_buy = 0 if len(state.order_depths[product].buy_orders.keys()) == 0 else max(state.order_depths[product].buy_orders.keys())

            if self.position[product] < 0:
                settled_pnl += self.position[product] * best_buy
            else:
                settled_pnl += self.position[product] * best_sell
            totpnl += settled_pnl + self.cpnl[product]
            #logger.print(f"For product {product}, {settled_pnl + self.cpnl[product]}, {(settled_pnl+self.cpnl[product])/(self.volume_traded[product]+1e-20)}")

        #logger.print(f"Timestamp {timestamp}, Total PNL ended up being {totpnl}")
        # String value holding Trader state data required. 
        # It will be delivered as TradingState.traderData on next execution.
        traderData = "SAMPLE" 
        
                # Sample conversion request. Check more details below. 
        conversions = 1
        #logger.flush(state, result, conversions, traderData)

        return result, conversions, traderData

if __name__ == '__main__':
    timestamp = 1100

    listings = {
        "GIFT_BASKET": Listing(
            symbol="GIFT_BASKET", 
            product="GIFT_BASKET", 
            denomination= "SEASHELLS"
        ),
        "CHOCOLATE": Listing(
            symbol="CHOCOLATE", 
            product="CHOCOLATE", 
            denomination= "SEASHELLS"
        ),
        "STRAWBERRIES": Listing(
            symbol="STRAWBERRIES", 
            product="STRAWBERRIES", 
            denomination= "SEASHELLS"
        ),
        "ROSES": Listing(
            symbol="ROSES", 
            product="ROSES", 
            denomination= "SEASHELLS"
        ),
        "STARFRUIT": Listing(
            symbol="STARFRUIT", 
            product="STARFRUIT", 
            denomination= "SEASHELLS"
        ),
        "ORCHIDS": Listing(
            symbol="ORCHIDS", 
            product="ORCHIDS", 
            denomination= "SEASHELLS"
        ),
        "AMETHYSTS": Listing(
            symbol="AMETHYSTS", 
            product="AMETHYSTS", 
            denomination= "SEASHELLS"
        ),
        "COCONUT_COUPON": Listing(
            symbol="COCONUT_COUPON", 
            product="COCONUT_COUPON", 
            denomination= "SEASHELLS"
        ),
        "COCONUT": Listing(
            symbol="COCONUT", 
            product="COCONUT", 
            denomination= "SEASHELLS"
        ),
    }

    order_depths = {
        "GIFT_BASKET": OrderDepth(
            buy_orders={10: 7, 9: 5},
            sell_orders={12: -5, 13: -3}
        ),
        "CHOCOLATE": OrderDepth(
            buy_orders={142: 3, 141: 5},
            sell_orders={144: -5, 145: -8}
        ),  
        "STRAWBERRIES": OrderDepth(
            buy_orders={142: 3, 141: 5},
            sell_orders={144: -5, 145: -8}
        ),
        "ROSES": OrderDepth(
            buy_orders={142: 3, 141: 5},
            sell_orders={144: -5, 145: -8}
        ),
        "STARFRUIT": OrderDepth(
            buy_orders={142: 3, 141: 5},
            sell_orders={144: -5, 145: -8}
        ),
        "AMETHYSTS": OrderDepth(
            buy_orders={142: 3, 141: 5},
            sell_orders={144: -5, 145: -8}
        ),
        "ORCHIDS": OrderDepth(
            buy_orders={142: 3, 141: 5},
            sell_orders={144: -5, 145: -8}
        ),
        "COCONUT_COUPON": OrderDepth(
            buy_orders={142: 3, 141: 5},
            sell_orders={144: -5, 145: -8}
        ),
        "COCONUT": OrderDepth(
            buy_orders={3: 3, 4: 5},
            sell_orders={10: -5, 15: -8}
        ),
    }

    own_trades = {
        "GIFT_BASKET": [
            Trade(
                symbol="GIFT_BASKET",
                price=11,
                quantity=4,
                buyer="SUBMISSION",
                seller="",
                timestamp=1000
            ),
            Trade(
                symbol="GIFT_BASKET",
                price=12,
                quantity=3,
                buyer="SUBMISSION",
                seller="",
                timestamp=1000
            )
        ],
        "CHOCOLATE": [
            Trade(
                symbol="CHOCOLATE",
                price=143,
                quantity=2,
                buyer="",
                seller="SUBMISSION",
                timestamp=1000
            ),
        ],
        "STRAWBERRIES":[
            Trade(
                symbol="STRAWBERRIES",
                price=143,
                quantity=2,
                buyer="",
                seller="SUBMISSION",
                timestamp=1000
            ),
        ],
        "ROSES": [
            Trade(
                symbol="ROSES",
                price=143,
                quantity=2,
                buyer="",
                seller="SUBMISSION",
                timestamp=1000
            ),
        ],
    }

    market_trades = {
        "GIFT_BASKET": [],
        "CHOCOLATE": [],
        "STRAWBERRIES": [],
        "ROSES": [],
        "STARFRUIT": [],
        "ORCHIDS": [],
        "AMETHYSTS": []
    }

    position = {
        "GIFT_BASKET": 10,
        "CHOCOLATE": -7,
        "STRAWBERRIES": -7,
        "ROSES": -7,
        "ORCHIDS": 20,
        "STARFRUIT" : 15,
        "AMETHYSTS" : -5,
        "COCONUT_COUPON" : 10,
        "COCONUT" : 20
    }

    observations = {}

    traderData = ""

    state = TradingState(
        traderData,
        timestamp,
        listings,
        order_depths,
        own_trades,
        market_trades,
        position,
        observations
    )

    trader = Trader()
    trader.run(state)