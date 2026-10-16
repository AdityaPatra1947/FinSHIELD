"""Finance taxonomy: categories, subcategories, merchants, income types, income brackets.

Everything here is data, not logic, so it can be shown in the UI and edited later.
need_want: 'need' (essential), 'want' (discretionary), 'social' (gifts/family; counted with wants in 50/30/20),
           'financial' (bank fees etc.; counted with needs).
"""
from __future__ import annotations

# code -> label, group (user-facing), need_want, subcategories {code: label}, fixed subcategory codes
CATEGORIES: dict[str, dict] = {
    "rent": dict(label="Housing", group="Essentials", nw="need",
                 subs={"rent": "Rent", "maintenance": "Maintenance", "property_tax": "Property tax"},
                 fixed={"rent", "maintenance", "property_tax"}),
    "utilities": dict(label="Utilities", group="Essentials", nw="need",
                      subs={"electricity": "Electricity", "water": "Water", "gas": "Gas", "internet": "Internet / TV",
                            "mobile": "Mobile"}, fixed={"water", "gas", "internet", "mobile"}),
    "groceries": dict(label="Groceries & household", group="Essentials", nw="need",
                      subs={"supermarket": "Supermarket", "quick_commerce": "Quick commerce", "dairy": "Milk & dairy",
                            "local_store": "Local store", "fresh": "Fresh produce", "household": "Household supplies"},
                      fixed=set()),
    "transport": dict(label="Transport", group="Essentials", nw="need",
                      subs={"cab": "Cab", "public": "Public transport", "fuel": "Fuel", "service": "Vehicle service",
                            "vehicle_insurance": "Vehicle insurance"}, fixed={"vehicle_insurance"}),
    "health": dict(label="Health", group="Essentials", nw="need",
                   subs={"medicines": "Medicines", "doctor": "Doctor visits", "diagnostics": "Diagnostics"}, fixed=set()),
    "insurance": dict(label="Insurance", group="Essentials", nw="need",
                      subs={"health_insurance": "Health insurance", "term_life": "Term life insurance",
                            "vehicle": "Vehicle insurance"}, fixed={"health_insurance", "term_life", "vehicle"}),
    "education": dict(label="Education", group="Essentials", nw="need",
                      subs={"courses": "Courses", "fees": "Fees", "books": "Books", "coaching": "Coaching"}, fixed=set()),
    "debt_emi": dict(label="Debt payments", group="Essentials", nw="need",
                     subs={"home_loan": "Home loan EMI", "vehicle_loan": "Vehicle loan EMI",
                           "personal_loan": "Personal loan EMI", "education_loan": "Education loan EMI",
                           "gadget_emi": "Gadget EMI"},
                     fixed={"home_loan", "vehicle_loan", "personal_loan", "education_loan", "gadget_emi"}),
    "household_help": dict(label="Domestic help & childcare", group="Essentials", nw="need",
                           subs={"domestic": "Domestic help", "childcare": "Childcare"}, fixed={"domestic", "childcare"}),
    "dining": dict(label="Eating out", group="Lifestyle", nw="want",
                   subs={"delivery": "Food delivery", "restaurant": "Restaurant", "cafe": "Cafe", "street": "Street food"},
                   fixed=set()),
    "shopping": dict(label="Shopping", group="Lifestyle", nw="want",
                     subs={"clothes": "Clothes", "gadgets": "Gadgets", "online": "Online shopping", "decor": "Home decor"},
                     fixed=set()),
    "entertainment": dict(label="Entertainment", group="Lifestyle", nw="want",
                          subs={"movies": "Movies", "games": "Games", "ott": "OTT subscription", "music": "Music",
                                "events": "Events"}, fixed={"ott"}),
    "travel": dict(label="Travel & holidays", group="Lifestyle", nw="want",
                   subs={"train": "Train", "flights": "Flights", "bus": "Bus", "stay": "Stay"}, fixed=set()),
    "personal_care": dict(label="Personal care", group="Lifestyle", nw="want",
                          subs={"salon": "Salon", "gym": "Gym", "wellness": "Wellness"}, fixed={"gym"}),
    "social": dict(label="Social & family", group="Social", nw="social",
                   subs={"gifts": "Gifts", "donations": "Donations", "festival": "Festivals & weddings",
                         "family_support": "Supporting family"}, fixed={"family_support"}),
    "fees": dict(label="Bank fees & penalties", group="Financial", nw="financial",
                 subs={"bank_fee": "Bank fee", "late_fee": "Late fee / penalty"}, fixed=set()),
}
# Order of the nine original generator categories (merchant keys m0..m53 use 6 merchants per category in this order)
GEN_ORDER = ["groceries", "dining", "transport", "shopping", "entertainment", "health", "utilities", "travel", "education"]

# (name, subcategory) x 6 per generator category
GEN_MERCHANTS: dict[str, list[tuple[str, str]]] = {
    "groceries": [("BigBasket", "supermarket"), ("DMart", "supermarket"), ("Zepto", "quick_commerce"),
                  ("Milkbasket", "dairy"), ("Local kirana", "local_store"), ("Fruit vendor", "fresh")],
    "dining": [("Swiggy", "delivery"), ("Zomato", "delivery"), ("Cafe Coffee Day", "cafe"),
               ("Local restaurant", "restaurant"), ("Street food stall", "street"), ("Dominos", "restaurant")],
    "transport": [("Uber", "cab"), ("Ola", "cab"), ("Metro card", "public"), ("Indian Oil", "fuel"),
                  ("Bharat Petroleum", "fuel"), ("Service centre", "service")],
    "shopping": [("Amazon", "online"), ("Flipkart", "online"), ("Myntra", "clothes"), ("Zara", "clothes"),
                 ("Croma", "gadgets"), ("IKEA", "decor")],
    "entertainment": [("PVR Cinemas", "movies"), ("Steam", "games"), ("Spotify top-up", "music"),
                      ("Bowling alley", "events"), ("Concert tickets", "events"), ("Play Store", "games")],
    "health": [("Apollo Pharmacy", "medicines"), ("Practo", "doctor"), ("1mg", "medicines"), ("Local clinic", "doctor"),
               ("Pathology lab", "diagnostics"), ("Dental clinic", "doctor")],
    "utilities": [("BESCOM", "electricity"), ("Water board", "water"), ("Indane Gas", "gas"), ("Airtel Fibre", "internet"),
                  ("Jio recharge", "mobile"), ("Tata Play", "internet")],
    "travel": [("IRCTC", "train"), ("MakeMyTrip", "flights"), ("RedBus", "bus"), ("Airbnb", "stay"), ("OYO", "stay"),
               ("Goibibo", "flights")],
    "education": [("Udemy", "courses"), ("Coursera", "courses"), ("School fees", "fees"), ("Bookstore", "books"),
                  ("Tuition centre", "coaching"), ("Online academy", "courses")],
}

# income_type -> (label, class)   (class follows the user's 'ways of earning')
INCOME_TYPES: dict[str, tuple[str, str]] = {
    "salary": ("Salary", "Active"), "overtime": ("Overtime", "Active"), "bonus": ("Bonus & incentives", "Active"),
    "commission": ("Commission", "Active"), "freelance": ("Freelancing", "Active"), "consulting": ("Consulting", "Active"),
    "gig": ("Gig work", "Active"), "tuition": ("Tuition / teaching", "Active"), "parttime": ("Part-time job", "Active"),
    "stipend": ("Internship stipend", "Active"),
    "shop_revenue": ("Shop / store revenue", "Business"), "online_business": ("Online business", "Business"),
    "partnership": ("Partnership profit", "Business"), "farm": ("Farm income", "Business"),
    "rent_income": ("Rent from property", "Passive"), "interest": ("Interest (FD / savings / bonds)", "Passive"),
    "dividend": ("Dividends", "Passive"), "mf_gain": ("Mutual fund gains", "Passive"), "royalty": ("Royalties", "Passive"),
    "content_revenue": ("Ad / content revenue", "Passive"),
    "capital_gain": ("Capital gains", "Capital gains"),
    "gift": ("Gifts", "Irregular"), "prize": ("Cash prizes", "Irregular"), "scholarship": ("Scholarship", "Irregular"),
    "tax_refund": ("Tax refund", "Irregular"), "cashback": ("Cashback", "Irregular"),
    "reimbursement": ("Reimbursements", "Irregular"), "resale": ("Sale of used items", "Irregular"),
    "inheritance": ("Inheritance", "Irregular"),
    "pension": ("Pension", "Benefits"), "govt_scheme": ("Government scheme", "Benefits"),
    "family_allowance": ("Family allowance", "Benefits"), "insurance_payout": ("Insurance payout", "Benefits"),
    "pf_withdrawal": ("PF withdrawal", "Benefits"),
}

# Configurable income brackets (monthly NET income in rupees). Stored in the DB and editable by an admin.
DEFAULT_BRACKETS = [
    dict(code="B1", label="Under ₹15k", min_inr=0, max_inr=15000, mode="simple",
         situation="Student or low income: most money goes to food, transport and basics.",
         emphasis=["Daily cash tracking", "Very simple screens", "Safe to spend today", "Small emergency buffer",
                   "Loan / borrowing tracking"]),
    dict(code="B2", label="₹15k – ₹40k", min_inr=15000, max_inr=40000, mode="simple",
         situation="First jobs, stipends, small earners.",
         emphasis=["Needs vs wants split", "Subscription tracker", "First emergency-fund goal", "UPI / SMS auto-import"]),
    dict(code="B3", label="₹40k – ₹1L", min_inr=40000, max_inr=100000, mode="advanced",
         situation="Stable salary, rent and EMIs begin.",
         emphasis=["Budgets", "EMI tracker", "SIP tracking", "Insurance", "Savings-rate target of 20% or more",
                   "Credit-card due dates"]),
    dict(code="B4", label="₹1L – ₹3L", min_inr=100000, max_inr=300000, mode="advanced",
         situation="Higher income with more investments and liabilities.",
         emphasis=["Net worth", "Asset allocation", "Tax planning (80C, HRA, NPS)", "Goal planning", "Credit utilisation"]),
    dict(code="B5", label="₹3L and above", min_inr=300000, max_inr=10**9, mode="advanced",
         situation="Wealth building with multiple income streams.",
         emphasis=["Portfolio tracking", "Capital gains & tax harvesting", "Real-estate income",
                   "Business vs personal split", "Multi-account / family views"]),
]

TAGS = ["birthday", "work trip", "festival", "family", "health", "emergency", "weekend", "gift", "office", "friends"]


def need_want(category: str | None) -> str | None:
    c = CATEGORIES.get(category or "")
    return c["nw"] if c else None


def sub_label(category: str | None, sub: str | None) -> str | None:
    c = CATEGORIES.get(category or "")
    return c["subs"].get(sub, sub) if c and sub else sub
