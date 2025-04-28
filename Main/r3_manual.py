import numpy as np

def generate_reserve_prices(n=10000):
    """Generates turtle reserve prices excluding [200, 250]."""
    prices = []
    while len(prices) < n:
        p = np.random.uniform(160, 320)
        if not (200 <= p <= 250):
            prices.append(p)
    return np.array(prices)

def scaled_pnl(bid, avg_bid):
    """Compute the scaled profit when bid is under average."""
    if bid >= avg_bid:
        return 320 - bid
    else:
        p = ((320 - avg_bid) / (320 - bid)) ** 3
        return (320 - bid) * p

def evaluate_flipper_bids(first_bid, second_bid, avg_second_bid, reserve_prices):
    profit = 0
    for reserve in reserve_prices:
        if first_bid >= reserve:
            # Assume we bid first, then second — turtle chooses min over reserve
            bid_used = min(first_bid, second_bid)
            profit += scaled_pnl(bid_used, avg_second_bid)
    return profit

def find_best_flipper_bids(avg_second_bid_guess=275):
    reserve_prices = generate_reserve_prices()
    best_first, best_second = None, None
    best_profit = float('-inf')

    for first_bid in range(160, 320):
        for second_bid in range(first_bid, 320):
            profit = evaluate_flipper_bids(first_bid, second_bid, avg_second_bid_guess, reserve_prices)
            if profit > best_profit:
                best_profit = profit
                best_first, best_second = first_bid, second_bid

    return best_first, best_second, best_profit

# Run it
first_bid, second_bid, total_profit = find_best_flipper_bids(avg_second_bid_guess=275)
print(f"✅ Best First Bid: {first_bid}")
print(f"✅ Best Second Bid: {second_bid}")
print(f"💰 Expected Total Profit: {total_profit:.2f}")
