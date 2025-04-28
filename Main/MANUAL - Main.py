import tkinter as tk
from tkinter import ttk, messagebox
import matplotlib.pyplot as plt
import networkx as nx

exchange_rates = {
    'Snowballs': {'Pizza': 1.45, 'Silicon Nuggets': 0.52, 'SeaShells': 0.72},
    'Pizza': {'Snowballs': 0.7, 'Silicon Nuggets': 0.31, 'SeaShells': 0.48},
    'Silicon Nuggets': {'Snowballs': 1.95, 'Pizza': 3.1, 'SeaShells': 1.49},
    'SeaShells': {'Snowballs': 1.34, 'Pizza': 1.98, 'Silicon Nuggets': 0.64}
}

start_currency = 'SeaShells'
start_amount = 500_000
max_trades = 5

best_results = {i: {"amount": 0, "path": [], "graph_path": []} for i in range(1, max_trades + 1)}

def dfs(currency, amount, trades_left, path, graph_path):
    if 1 <= trades_left <= max_trades and currency == start_currency:
        if amount > best_results[trades_left]["amount"]:
            best_results[trades_left] = {
                "amount": amount,
                "path": path[:],
                "graph_path": graph_path[:]
            }

    if trades_left == max_trades:
        return

    for next_currency, rate in exchange_rates.get(currency, {}).items():
        new_amount = amount * rate
        log = f"Trade {currency} → {next_currency} | Rate: {rate} | {amount:.2f} → {new_amount:.2f}"
        dfs(next_currency, new_amount, trades_left + 1, path + [log], graph_path + [(currency, next_currency)])

def run_optimizer():
    for k in best_results:
        best_results[k]["amount"] = 0
        best_results[k]["path"].clear()
        best_results[k]["graph_path"].clear()

    dfs(start_currency, start_amount, 0, [], [])

    output_box.delete(1.0, tk.END)
    for k in range(1, max_trades + 1):
        result = best_results[k]
        if result["amount"] > 0:
            output_box.insert(tk.END, f"🔁 {k} Trade(s) → {result['amount']:.2f} SeaShells\n")
            output_box.insert(tk.END, "\n".join(result['path']) + "\n\n")
        else:
            output_box.insert(tk.END, f"🔁 {k} Trade(s) → No profitable cycle\n\n")

def show_graph_for_trades(trades):
    if trades not in best_results or best_results[trades]["amount"] == 0:
        messagebox.showinfo("No Result", f"No result for {trades} trades yet!")
        return

    result = best_results[trades]
    G = nx.DiGraph()

    for edge in result["graph_path"]:
        G.add_edge(*edge)

    pos = nx.spring_layout(G, seed=42)
    plt.figure(figsize=(8, 5))
    nx.draw(G, pos, with_labels=True, node_size=2500, node_color="skyblue", arrows=True, font_size=10, font_weight="bold")
    edge_labels = {(u, v): f"{exchange_rates[u][v]}" for u, v in G.edges()}
    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels)
    plt.title(f"Trade Graph for {trades} Trade(s)")
    plt.show()

# GUI Setup
root = tk.Tk()
root.title("Smart Currency Trade Optimizer")

frame = ttk.Frame(root, padding="20")
frame.grid(row=0, column=0)

ttk.Label(frame, text="💱 Trade Optimizer with Visuals (1–5 Trades)", font=("Arial", 16)).grid(row=0, column=0, columnspan=3, pady=10)

ttk.Button(frame, text="🚀 Run Optimizer", command=run_optimizer).grid(row=1, column=0, padx=5, pady=10)

# Dynamic Graph Buttons for 1 to 5 trades
for i in range(1, max_trades + 1):
    ttk.Button(frame, text=f"📈 Graph for {i} Trade(s)", command=lambda i=i: show_graph_for_trades(i)).grid(row=1, column=i, padx=5)

output_box = tk.Text(frame, height=25, width=100, wrap=tk.WORD)
output_box.grid(row=2, column=0, columnspan=6, pady=10)

root.mainloop()
