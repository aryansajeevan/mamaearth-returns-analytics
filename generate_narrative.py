# Part 3: SCR narrative from findings.json
# run from the repo root: python narrator/generate_narrative.py
# if GEMINI_API_KEY is set it calls Gemini, if not it uses the offline template

import json
import os
from datetime import datetime

# model names get retired often, so it can be changed without editing the code:
# export GEMINI_MODEL="some-other-model"
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")

SYSTEM_INSTRUCTION = (
    "You are a senior data analyst writing for Mamaearth's regional ops and finance heads. "
    "Write the report in exactly three labeled sections: Situation, Complication, Resolution. "
    "Every number in your output must come from the supplied findings and appear with the same value. "
    "Do not invent any statistics."
)


def month_name(ym):
    return datetime.strptime(ym, "%Y-%m").strftime("%B")


def generate_scr_narrative(findings):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("No GEMINI_API_KEY found, using the offline version.\n")
        return generate_scr_narrative_offline(findings)

    rates = findings["return_rate_by_payment"]
    seg = findings["highest_risk_segment"]
    peak = findings["true_peak_month"]
    jan = findings["outlier_inflated_month"]

    # numbers are filled in from the findings dict, nothing is typed in by hand
    prompt = (
        f"Write the SCR narrative using only these findings:\n"
        f"- Cleaned total revenue: INR {findings['cleaned_total_revenue_inr']:,.2f}\n"
        f"- Raw total revenue before cleaning: INR {findings['raw_total_revenue_inr']:,.2f}\n"
        f"- Difference caused by removing duplicate orders: INR {findings['duplicate_reconciliation_delta_inr']:,.2f}\n"
        f"- Return rate by payment method: COD {rates['COD']}%, CARD {rates['CARD']}%, UPI {rates['UPI']}%\n"
        f"- Highest risk segment: {seg['payment_method']} in Tier-{seg['city_tier']} cities, return rate {seg['return_rate_pct']}%\n"
        f"- True peak month: {month_name(peak['month'])} with revenue INR {peak['revenue_inr']:,.2f}\n"
        f"- {month_name(jan['month'])} looked like the peak at INR {jan['apparent_revenue_inr']:,.2f} but is really "
        f"INR {jan['corrected_revenue_inr']:,.2f} after removing two bulk orders\n"
    )

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=90000))  # 30 seconds
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0.0,        # factual business report, so no randomness wanted
                max_output_tokens=2000,   # newer models use some of this for thinking, so it is set high
            ),
        )
        if not response.text:
            raise ValueError("Gemini returned an empty answer")
        return {
            "status": "success",
            "narrative": response.text,
            "tokens": response.usage_metadata.total_token_count,
        }
    except Exception as err:
        result = {"status": "error", "narrative": None, "message": str(err)}
        print("Gemini call failed:", result["message"])
        print("Using the offline version instead.\n")
        return generate_scr_narrative_offline(findings)


def generate_scr_narrative_offline(findings):
    rates = findings["return_rate_by_payment"]
    seg = findings["highest_risk_segment"]
    peak = findings["true_peak_month"]
    jan = findings["outlier_inflated_month"]

    text = (
        f"Situation: After cleaning the order data, total revenue is INR {findings['cleaned_total_revenue_inr']:,.2f}. "
        f"This is INR {findings['duplicate_reconciliation_delta_inr']:,.2f} lower than the raw total of "
        f"INR {findings['raw_total_revenue_inr']:,.2f}, and the whole difference comes from duplicate "
        f"double-submitted orders. {month_name(peak['month'])} is the real peak month with "
        f"INR {peak['revenue_inr']:,.2f}.\n\n"
        f"Complication: Returns are not spread evenly. COD orders are returned {rates['COD']}% of the time, "
        f"compared with {rates['CARD']}% for card and {rates['UPI']}% for UPI. The worst segment is "
        f"{seg['payment_method']} orders in Tier-{seg['city_tier']} cities at {seg['return_rate_pct']}%. "
        f"{month_name(jan['month'])} looked like the best month (INR {jan['apparent_revenue_inr']:,.2f}) but this "
        f"was only because of two bulk orders; without them it is INR {jan['corrected_revenue_inr']:,.2f}.\n\n"
        f"Resolution: Regional ops should focus first on {seg['payment_method']} orders in Tier-{seg['city_tier']} "
        f"cities, for example with confirmation calls or by pushing prepaid payment. Finance should plan using "
        f"INR {findings['cleaned_total_revenue_inr']:,.2f} as the revenue base and not treat the "
        f"{month_name(jan['month'])} bulk orders as a trend."
    )
    return {"status": "success", "narrative": text, "tokens": None}


def check_numbers(narrative, findings):
    # checks that the five required figures are in the text (commas removed first)
    text = narrative.replace(",", "")
    cleaned = findings["cleaned_total_revenue_inr"]
    delta = findings["duplicate_reconciliation_delta_inr"]
    cod = findings["return_rate_by_payment"]["COD"]
    seg_rate = findings["highest_risk_segment"]["return_rate_pct"]
    peak = findings["true_peak_month"]

    checks = {
        "cleaned total revenue": f"{cleaned:.2f}" in text or str(cleaned) in text,
        "COD return rate": str(cod) in text,
        "COD + Tier-2 return rate": str(seg_rate) in text,
        "duplicate delta": f"{delta:.2f}" in text or str(delta) in text,
        "true peak month + revenue": month_name(peak["month"]) in text
                                     and (f"{peak['revenue_inr']:.2f}" in text or str(peak["revenue_inr"]) in text),
    }
    for name, ok in checks.items():
        print(("PASS" if ok else "FAIL") + " - " + name)
    return all(checks.values())


if __name__ == "__main__":
    with open("narrator/findings.json") as f:
        findings = json.load(f)

    result = generate_scr_narrative(findings)
    print("Written by:", "Gemini" if result["tokens"] else "offline template")
    print(result["narrative"])
    print("\nChecking the figures:")
    check_numbers(result["narrative"], findings)
