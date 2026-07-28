import random
from collections import Counter

# Case configuration
items = ["nodes_30000", "master_key", "founder_token", "dev_trophy", "meow_cat", "discord_nitro"]
weights = [40, 30, 20, 8, 1.99999, 0.00001]

TOTAL_OPENINGS = 5_000_000

# Simulate opening the case 100,000 times
# random.choices picks items according to their assigned weights
results = random.choices(items, weights=weights, k=TOTAL_OPENINGS)

# Count occurrences of each item
counts = Counter(results)

# Print formatted summary
print(f"--- Legendary Case Simulation ({TOTAL_OPENINGS:,} Openings) ---\n")
print(f"{'Item':<20} | {'Count':<10} | {'Simulated %':<12} | {'Expected %'}")
print("-" * 60)

for item, weight in zip(items, weights):
    count = counts[item]
    simulated_pct = (count / TOTAL_OPENINGS) * 100
    expected_pct = (weight / sum(weights)) * 100
    
    print(f"{item:<20} | {count:<10,} | {simulated_pct:>10.2f}% | {expected_pct:>9.2f}%")