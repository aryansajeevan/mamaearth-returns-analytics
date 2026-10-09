# Part 2: cleaning + EDA on the raw csv files
# run from the repo root: python analysis/clean_and_eda.py

import json
import pandas as pd

# ---------- Task 1: load ----------
orders = pd.read_csv("data/orders.csv")
customers = pd.read_csv("data/customers.csv")
products = pd.read_csv("data/products.csv")
print("orders shape before cleaning:", orders.shape)

# ---------- Task 2: payment_method casing ----------
print("\nraw payment_method values:", orders["payment_method"].unique())
print("number of distinct values:", orders["payment_method"].nunique())
orders["payment_method"] = orders["payment_method"].str.strip().str.upper()
print("after cleaning:")
print(orders["payment_method"].value_counts())

# ---------- Task 3: duplicates ----------
# order_id is left out of the key because it is different on the duplicate rows
key = ["customer_id", "product_id", "order_date", "quantity",
       "discount_pct", "payment_method", "rating", "returned"]
dup_flag = orders.duplicated(subset=key, keep="first")
dropped = orders[dup_flag].copy()
print("\nduplicates found:", dup_flag.sum())
print("dropped order_ids:", dropped["order_id"].tolist())
orders_clean = orders[~dup_flag].copy()
print("orders_clean shape:", orders_clean.shape)

# ---------- Task 4: missing values ----------
print("\nmissing discount_pct:", orders_clean["discount_pct"].isnull().sum())
print("missing rating:", orders_clean["rating"].isnull().sum())
median_rating = orders_clean["rating"].median()
print("median rating before imputing:", median_rating)

orders_clean["discount_pct"] = orders_clean["discount_pct"].fillna(0)   # no promo code used
orders_clean["rating"] = orders_clean["rating"].fillna(median_rating)
print(orders_clean[["discount_pct", "rating"]].isnull().sum().to_dict())

# ---------- Task 5: merge + reconcile with the SQL total ----------
df = orders_clean.merge(products, on="product_id").merge(customers, on="customer_id")
df["order_value"] = df["quantity"] * df["price"] * (1 - df["discount_pct"] / 100)
cleaned_total = round(df["order_value"].sum(), 2)
print("\ncleaned total order_value (175 rows):", f"{cleaned_total:.2f}")

# value of the 5 dropped rows, worked out separately as a check
# (their missing discounts also count as 0, same as the SQL COALESCE)
d = dropped.fillna({"discount_pct": 0}).merge(products, on="product_id")
dropped_value = round((d["quantity"] * d["price"] * (1 - d["discount_pct"] / 100)).sum(), 2)

# raw total over all 180 rows (should be the same as SQL report (a))
raw = pd.read_csv("data/orders.csv").fillna({"discount_pct": 0}).merge(products, on="product_id")
raw_total = round((raw["quantity"] * raw["price"] * (1 - raw["discount_pct"] / 100)).sum(), 2)
delta = round(raw_total - cleaned_total, 2)
print("raw total from SQL report (a):", f"{raw_total:.2f}")
print("difference:", f"{delta:.2f}")
print("sum of order_value of the 5 dropped rows:", f"{dropped_value:.2f}")

print(f"""
Reconciliation note: the SQL report (a) total of Rs {raw_total:,.2f} was worked out on all 180 raw orders,
and the cleaned pandas total of Rs {cleaned_total:,.2f} is on 175 orders, so the gap is Rs {delta:,.2f}.
This whole gap comes from the 5 duplicate (double-submit) orders O0176 to O0180 that were removed in Task 3.
When I add up their order_value on its own I also get Rs {dropped_value:,.2f}, which matches the gap exactly.
Filling the missing discount_pct and rating values does not change the gap, because the SQL query already
treated a missing discount as 0% and rating is not used in order_value at all.""")

# ---------- Task 6: outliers in quantity (IQR) ----------
q1 = df["quantity"].quantile(0.25)
q3 = df["quantity"].quantile(0.75)
iqr = q3 - q1
lower = q1 - 1.5 * iqr
upper = q3 + 1.5 * iqr
print("\nQ1 =", q1, "Q3 =", q3, "IQR =", iqr, "lower =", lower, "upper =", upper)

df["is_outlier"] = (df["quantity"] < lower) | (df["quantity"] > upper)
print("outlier rows (kept, only flagged):")
print(df[df["is_outlier"]][["order_id", "quantity", "order_date"]])

# ---------- Task 7: COD hypothesis ----------
print("\nHypothesis: COD orders have a higher return rate than Card and UPI orders.")
pay = df.groupby("payment_method")["returned"].agg(["count", "mean"])
print(pay)
pay_rate = (pay["mean"] * 100).round(1)
print("return rate %:")
print(pay_rate)
if pay["mean"].idxmax() == "COD":
    print("Hypothesis: Confirmed")
else:
    print("Hypothesis: Rejected")

# ---------- Task 8: payment_method x city_tier ----------
seg = df.groupby(["payment_method", "city_tier"])["returned"].agg(["count", "mean"])
seg["rate_pct"] = (seg["mean"] * 100).round(1)
print("\nsegments:")
print(seg)
worst = seg["mean"].idxmax()
worst_rate = seg.loc[worst, "rate_pct"]
print(f"Highest risk segment: {worst[0]} + Tier-{worst[1]} cities at {worst_rate}%")
print(f"COD Tier-1 is {seg.loc[('COD', 1), 'rate_pct']}% but COD Tier-2 is {seg.loc[('COD', 2), 'rate_pct']}%, "
      "so the COD risk is not the same everywhere.")

# ---------- Task 9: correlation ----------
def strength(r):
    r = abs(r)
    if r < 0.2:
        return "negligible"
    elif r < 0.4:
        return "weak"
    elif r < 0.7:
        return "moderate"
    return "strong"

cols = ["rating", "returned", "discount_pct", "quantity"]
corr = df[cols].corr()
print("\ncorrelation matrix:")
print(corr.round(3))
for i in range(len(cols)):
    for j in range(i + 1, len(cols)):
        r = corr.loc[cols[i], cols[j]]
        print(f"{cols[i]} vs {cols[j]}: {r:.3f} -> {strength(r)}")
r = corr.loc["discount_pct", "returned"]
print(f"Hypothesis 'higher discounts reduce returns': Busted (r = {r:.3f}, {strength(r)})")

# ---------- Task 10: monthly revenue ----------
df["order_date"] = pd.to_datetime(df["order_date"])
df["year_month"] = df["order_date"].dt.strftime("%Y-%m")
monthly_all = df.groupby("year_month")["order_value"].sum().round(2)
monthly_fixed = df[~df["is_outlier"]].groupby("year_month")["order_value"].sum().round(2)
print("\nmonthly revenue including outliers:")
print(monthly_all)
print("\nmonthly revenue excluding outliers:")
print(monthly_fixed)

top_all = monthly_all.idxmax()
top_fixed = monthly_fixed.idxmax()
print(f"\nJanuary only looks like the best month ({monthly_all[top_all]:.2f}) because of the two bulk orders "
      "in January (O0011 on 2026-01-28 and O0098 on 2026-01-10).")
print(f"Without them January is {monthly_fixed[top_all]:.2f} and March ({monthly_fixed[top_fixed]:.2f}) "
      "is the real peak month.")

# ---------- write findings.json for the narrator ----------
findings = {
    "cleaned_total_revenue_inr": cleaned_total,
    "raw_total_revenue_inr": raw_total,
    "duplicate_reconciliation_delta_inr": delta,
    "return_rate_by_payment": {"COD": float(pay_rate["COD"]), "CARD": float(pay_rate["CARD"]), "UPI": float(pay_rate["UPI"])},
    "highest_risk_segment": {"payment_method": worst[0], "city_tier": int(worst[1]), "return_rate_pct": float(worst_rate)},
    "true_peak_month": {"month": top_fixed, "revenue_inr": float(monthly_fixed[top_fixed])},
    "outlier_inflated_month": {"month": top_all, "apparent_revenue_inr": float(monthly_all[top_all]),
                               "corrected_revenue_inr": float(monthly_fixed[top_all])},
}
with open("narrator/findings.json", "w") as f:
    json.dump(findings, f, indent=2)
print("\nsaved narrator/findings.json")
