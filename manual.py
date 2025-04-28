import itertools
import random

# Set seed for reproducibility
random.seed(42)

# Base treasure
BASE_TREASURE = 10000

# Opening costs for 1st, 2nd, and 3rd suitcase respectively
OPEN_COSTS = [0, 50, 100]

# Each suitcase: (label, multiplier, number_of_contestants)
suitcases = [
    ("A1", 80, 6), ("A2", 50, 4), ("A3", 83, 7), ("A4", 31, 2), ("A5", 60, 4),
    ("B1", 89, 8), ("B2", 10, 1), ("B3", 37, 3), ("B4", 70, 4), ("B5", 90, 10),
    ("C1", 17, 1), ("C2", 40, 3), ("C3", 73, 4), ("C4", 100, 15), ("C5", 20, 2),
    ("D1", 41, 3), ("D2", 79, 5), ("D3", 23, 2), ("D4", 47, 3), ("D5", 30, 2),
]

# Simulate selection probabilities based on 10000 rounds
simulated_counts = {label: 0 for label, _, _ in suitcases}
num_simulations = 10000

# Randomly simulate suitcase selections to estimate probabilities
for _ in range(num_simulations):
    selected = random.choice(suitcases)
    simulated_counts[selected[0]] += 1

# Total selections
total_selections = sum(simulated_counts.values())

# Compute estimated probabilities
selection_probs = {label: count / total_selections for label, count in simulated_counts.items()}

def expected_profit(combo):
    total_value = 0
    combo_labels = [label for label, _, _ in combo]
    opening_cost = OPEN_COSTS[len(combo) - 1]
    for label, multiplier, contestants in combo:
        freq_ratio = selection_probs[label]
        value = (BASE_TREASURE * multiplier) / (contestants + freq_ratio * total_selections)
        total_value += value
    profit = total_value - opening_cost
    return profit, combo_labels

# Try all combinations of 1, 2, or 3 suitcases
best_profit = float("-inf")
best_combo = []

for k in [1, 2, 3]:
    for combo in itertools.combinations(suitcases, k):
        profit, labels = expected_profit(combo)
        if profit > best_profit:
            best_profit = profit
            best_combo = labels
print(f"Best combination: {best_combo} with expected profit: {best_profit}")

