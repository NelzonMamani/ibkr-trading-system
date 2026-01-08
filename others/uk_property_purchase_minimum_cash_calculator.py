"""
UK Property Purchase – Minimum Cash Requirement Calculator
Applies to England & Northern Ireland only.

This script calculates:
• Deposit
• Mortgage required
• Stamp Duty Land Tax (SDLT)
• Additional purchase costs
• Total minimum cash required

Two scenarios are shown:
A) First-Time Buyer (Individual)
B) Limited Company Buyer

All numeric values are configurable below.
"""

# ============================================================
# CONFIGURATION SECTION — EASY TO MODIFY
# ============================================================

# --- Deposit assumptions (typical lender requirements) ---
first_time_buyer_deposit_rate = 0.05        # 5%
company_buyer_deposit_rate = 0.25           # 25%

# --- First-time buyer SDLT rules ---
first_time_buyer_sdlt_zero_rate_limit = 300_000
first_time_buyer_sdlt_upper_limit = 500_000
first_time_buyer_sdlt_rate_above_threshold = 0.05

# --- Standard SDLT rates (simplified for company example) ---
standard_sdlt_zero_rate_limit = 250_000
standard_sdlt_rate_above_threshold = 0.05
additional_property_surcharge_rate = 0.03   # 3% surcharge for companies

# --- Additional purchase costs (estimates) ---
mortgage_broker_fee = 750
solicitor_conveyancing_cost = 1_500
mortgage_arrangement_fee = 1_000
valuation_survey_cost = 500

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def format_currency(amount):
    """Format number as GBP currency."""
    return f"£{amount:,.2f}"


def calculate_additional_costs():
    """Return total additional purchase costs."""
    return (
        mortgage_broker_fee +
        solicitor_conveyancing_cost +
        mortgage_arrangement_fee +
        valuation_survey_cost
    )


# ============================================================
# MAIN CALCULATION
# ============================================================

print("=" * 72)
print(" UK PROPERTY PURCHASE – WORKED FINANCIAL CALCULATION (ENGLAND)")
print("=" * 72)

# --- User input with validation ---
while True:
    try:
        property_price = float(input("Enter property price (£): "))
        if property_price <= 0:
            raise ValueError
        break
    except ValueError:
        print("Please enter a valid positive number.")

print("\nGiven:")
print(f"Property Price = {format_currency(property_price)}")

# ============================================================
# SECTION A — FIRST-TIME BUYER
# ============================================================

print("\n" + "-" * 72)
print("SECTION A — FIRST-TIME BUYER (INDIVIDUAL)")
print("-" * 72)

# Deposit
first_time_buyer_deposit = property_price * first_time_buyer_deposit_rate
first_time_buyer_mortgage = property_price - first_time_buyer_deposit

print("\n1. Deposit Calculation")
print(f"Deposit = 5% × {format_currency(property_price)} "
      f"= {format_currency(first_time_buyer_deposit)}")

print("\n2. Mortgage Amount Required")
print(f"Mortgage = Property Price − Deposit "
      f"= {format_currency(first_time_buyer_mortgage)}")

# Stamp Duty
print("\n3. Stamp Duty Land Tax (SDLT)")

if property_price <= first_time_buyer_sdlt_zero_rate_limit:
    sdlt_first_time = 0
    print("Property price ≤ £300,000 → SDLT = £0.00")
else:
    taxable_amount = min(
        property_price,
        first_time_buyer_sdlt_upper_limit
    ) - first_time_buyer_sdlt_zero_rate_limit

    sdlt_first_time = taxable_amount * first_time_buyer_sdlt_rate_above_threshold

    print(f"Taxable Amount = {format_currency(property_price)} − £300,000 "
          f"= {format_currency(taxable_amount)}")
    print(f"SDLT = 5% × {format_currency(taxable_amount)} "
          f"= {format_currency(sdlt_first_time)}")

# Additional costs
additional_costs = calculate_additional_costs()

print("\n4. Additional Purchase Costs")
print(f"Mortgage Broker Fee       = {format_currency(mortgage_broker_fee)}")
print(f"Solicitor / Conveyancing = {format_currency(solicitor_conveyancing_cost)}")
print(f"Mortgage Arrangement Fee = {format_currency(mortgage_arrangement_fee)}")
print(f"Valuation / Survey       = {format_currency(valuation_survey_cost)}")
print(f"Additional Costs Total   = {format_currency(additional_costs)}")

# Total cash
total_cash_first_time = (
    first_time_buyer_deposit +
    sdlt_first_time +
    additional_costs
)

print("\n5. Total Minimum Cash Required")
print("Total Cash Needed = Deposit + Stamp Duty + Additional Costs")
print(f"                  = {format_currency(first_time_buyer_deposit)} + "
      f"{format_currency(sdlt_first_time)} + {format_currency(additional_costs)}")
print(f"                  = {format_currency(total_cash_first_time)}")

# ============================================================
# SECTION B — LIMITED COMPANY
# ============================================================

print("\n" + "-" * 72)
print("SECTION B — LIMITED COMPANY PURCHASE")
print("-" * 72)

# Deposit
company_deposit = property_price * company_buyer_deposit_rate
company_mortgage = property_price - company_deposit

print("\n1. Deposit Calculation")
print(f"Deposit = 25% × {format_currency(property_price)} "
      f"= {format_currency(company_deposit)}")

print("\n2. Mortgage Amount Required")
print(f"Mortgage = Property Price − Deposit "
      f"= {format_currency(company_mortgage)}")

# Stamp Duty with surcharge
print("\n3. Stamp Duty Land Tax (SDLT)")

if property_price <= standard_sdlt_zero_rate_limit:
    base_sdlt = 0
else:
    taxable_amount_company = property_price - standard_sdlt_zero_rate_limit
    base_sdlt = taxable_amount_company * standard_sdlt_rate_above_threshold

surcharge = property_price * additional_property_surcharge_rate
sdlt_company = base_sdlt + surcharge

print(f"Base SDLT = 5% × (Property − £250,000)")
print(f"Surcharge = 3% × {format_currency(property_price)} "
      f"= {format_currency(surcharge)}")
print(f"Total SDLT = Base SDLT + Surcharge = {format_currency(sdlt_company)}")

# Total cash
total_cash_company = (
    company_deposit +
    sdlt_company +
    additional_costs
)

print("\n4. Total Minimum Cash Required")
print("Total Cash Needed = Deposit + Stamp Duty + Additional Costs")
print(f"                  = {format_currency(company_deposit)} + "
      f"{format_currency(sdlt_company)} + {format_currency(additional_costs)}")
print(f"                  = {format_currency(total_cash_company)}")

# ============================================================
# END NOTES
# ============================================================

print("\n" + "=" * 72)
print("NOTES:")
print("• Deposit percentages and fees are typical market assumptions.")
print("• SDLT rules apply to England & Northern Ireland only.")
print("• Figures are estimates — always confirm with professionals.")
print("=" * 72)
