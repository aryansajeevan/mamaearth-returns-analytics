# Part 2, Task 11: the two charts
# run from the repo root after clean_and_eda.py: python analysis/visualize.py

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker

# same cleaning steps as clean_and_eda.py, repeated here so this script runs on its own
orders = pd.read_csv("data/orders.csv")
customers = pd.read_csv("data/customers.csv")
products = pd.read_csv("data/products.csv")

orders["payment_method"] = orders["payment_method"].str.strip().str.upper()
key = ["customer_id", "product_id", "order_date", "quantity",
       "discount_pct", "payment_method", "rating", "returned"]
orders = orders[~orders.duplicated(subset=key, keep="first")].copy()
orders["discount_pct"] = orders["discount_pct"].fillna(0)
orders["rating"] = orders["rating"].fillna(orders["rating"].median())

df = orders.merge(products, on="product_id").merge(customers, on="customer_id")
df["order_value"] = df["quantity"] * df["price"] * (1 - df["discount_pct"] / 100)

q1, q3 = df["quantity"].quantile(0.25), df["quantity"].quantile(0.75)
iqr = q3 - q1
df["is_outlier"] = (df["quantity"] < q1 - 1.5 * iqr) | (df["quantity"] > q3 + 1.5 * iqr)

# colours used in both charts
RED = "#E4572E"
BLUE = "#4C78A8"
GREEN = "#2A9D8F"
GREY = "#6B7280"

def clean_axes(ax):
    # remove the top and right border so the chart looks lighter
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", alpha=0.25)
    ax.set_axisbelow(True)

# ---- chart 1: return rate by payment method ----
rates = (df.groupby("payment_method")["returned"].mean() * 100).round(1)
rates = rates.sort_values(ascending=False)
times = rates["COD"] / rates["CARD"]

fig, ax = plt.subplots(figsize=(8, 5.5))
colors = [RED if m == "COD" else BLUE for m in rates.index]
bars = ax.bar(rates.index, rates.values, color=colors, width=0.55)
for bar, value in zip(bars, rates.values):
    ax.text(bar.get_x() + bar.get_width() / 2, value + 1, f"{value}%",
            ha="center", fontsize=14, fontweight="bold")
ax.set_title(f"COD Returns at {rates['COD']}% \u2014 {times:.0f}x Card",
             fontsize=17, fontweight="bold", loc="left", pad=18)
ax.set_xlabel("Payment method", fontsize=11)
ax.set_ylabel("Return rate (%)", fontsize=11)
ax.set_ylim(0, rates.max() * 1.18)
clean_axes(ax)
fig.tight_layout()
fig.savefig("visualizations/return_rate_by_payment.png", dpi=150)
plt.close(fig)

# ---- chart 2: monthly revenue without the outliers ----
df["year_month"] = pd.to_datetime(df["order_date"]).dt.strftime("%Y-%m")
monthly = df[~df["is_outlier"]].groupby("year_month")["order_value"].sum().round(2)
peak = monthly.idxmax()

fig, ax = plt.subplots(figsize=(9, 5.5))
ax.plot(monthly.index, monthly.values, color=GREY, linewidth=2.5, marker="o", markersize=8, zorder=2)
ax.fill_between(monthly.index, monthly.values, color=GREY, alpha=0.08)
ax.scatter([peak], [monthly[peak]], color=GREEN, s=220, zorder=3)   # highlight the peak month
for month, value in monthly.items():
    ax.text(month, value + 1200, f"\u20b9{value:,.0f}", ha="center", fontsize=11,
            fontweight="bold" if month == peak else "normal",
            color=GREEN if month == peak else "black")
ax.set_title(f"Outlier-Corrected Monthly Revenue \u2014 Peak Month is {peak}",
             fontsize=14.5, fontweight="bold", loc="left", pad=18)
ax.set_xlabel("Month", fontsize=11)
ax.set_ylabel("Revenue (INR)", fontsize=11)
ax.set_ylim(0, monthly.max() * 1.2)
ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, pos: f"{x:,.0f}"))
clean_axes(ax)
fig.tight_layout()
fig.savefig("visualizations/monthly_revenue_trend.png", dpi=150)
plt.close(fig)

print("saved both charts in visualizations/")
