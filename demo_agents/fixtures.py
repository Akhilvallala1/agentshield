# Synthetic. The policy number, badge, and claim ID are the "novel" entities gen 0 misses.
GOLDEN_MESSAGE = (
    "Hi, this is Maria Gonzalez. My car was hit in a parking lot. Policy INS-AZ-4471-K. "
    "Adjuster ADJ#77-1043 came by and said claim CLM-2026-000913 is pending. "
    "You can call me at (415) 555-0134."
)
GOLDEN_SESSION = "demo-session-001"

# Drift: marketing launches a product line whose codes look exactly like policy numbers (synthetic, no PII).
DRIFT_MESSAGES = [
    "New brochure for product INS-TX-0042-A ships Monday to all branches.",
    "Marketing wants the INS-CA-1100-B bundle featured on the homepage banner.",
    "Inventory note: 400 printed flyers for plan INS-NY-0300-C arrived at the Reno warehouse.",
    "Please add product code INS-FL-0777-D to the spring catalog price list.",
    "Training deck slide 4 still lists the old INS-WA-0101-E family plan.",
    "Pricing team approved a 5% discount on the INS-OR-0220-F starter package.",
]
DRIFT_SESSION = "drift-session-001"
