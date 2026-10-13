"""The demo scenario as pure data: a scripted mule-network laundering operation.

Used by scripts/demo_plant.py to plant it (into a copy of the real data, or into
the standalone demo database) and by the app to explain it: which stage each
transaction belongs to, each account's role, and the rules each stage is meant
to trigger. No database access here, so anything can import it.

  1. Collection     9 feeders pay a mule account opened 6 days earlier, within 25 minutes   R3, R4
  2. Consolidation  the mule forwards ~97% to a collector in one transfer                    R1
  3. Layering       collector -> shell 1 -> shell 2 -> collector, each hop under Rs 1,00,000  R6
  4. Cash-out       9 transfers just under Rs 1,00,000 to 9 cash-out accounts in 8 minutes   R2, R5
"""
from datetime import datetime, timedelta

PREFIX = "DEMO-"
# Upper bound for a case-sensitive prefix match that can still use the uid
# indexes: uid >= PREFIX and uid < PREFIX_END. Not LIKE 'DEMO-%': SQLite's LIKE
# ignores case, so it would also match a real account named "demo-...".
PREFIX_END = PREFIX[:-1] + chr(ord(PREFIX[-1]) + 1)   # "DEMO."
# Ordinary activity planted around the scenario in the demo copy (never in the standalone demo)
BACKGROUND_PREFIX = f"{PREFIX}BG"
BACKGROUND_END = BACKGROUND_PREFIX[:-1] + chr(ord(BACKGROUND_PREFIX[-1]) + 1)   # "DEMO-BH"

BASE = datetime(2024, 11, 14, 1, 30)   # a night inside the synthetic data's 2024 range

FEEDERS = [f"{PREFIX}FEED{i:02d}" for i in range(1, 10)]
MULE = f"{PREFIX}MULE"
COLLECTOR = f"{PREFIX}COLLECTOR"
SHELLS = [f"{PREFIX}SHELL1", f"{PREFIX}SHELL2"]
CASHOUTS = [f"{PREFIX}CASH{i:02d}" for i in range(1, 10)]

ROLES = {
    **{u: "feeder" for u in FEEDERS},
    MULE: "mule",
    COLLECTOR: "collector",
    **{u: "shell" for u in SHELLS},
    **{u: "cash-out" for u in CASHOUTS},
}
NAMES = [
    "Ritika Bansal", "Harish Kulkarni", "Meera Pillai", "Sanjay Rawat", "Ayesha Khan",
    "Gopal Iyer", "Nandini Rao", "Vikram Sethi", "Pooja Chawla",          # feeders
    "Kabir Malhotra",                                                      # mule
    "Raghav Oberoi",                                                       # collector
    "Sterling Traders", "Lotus Exim Services",                             # shells
    "Imran Shaikh", "Deepa Menon", "Tarun Gill", "Lakshmi Reddy", "Aman Bedi",
    "Sunita Joshi", "Farhan Qureshi", "Kavya Nair", "Rohit Dhawan",        # cash-outs
]
STAGES = ["1 Collection", "2 Consolidation", "3 Layering", "4 Cash-out"]

# What each stage shows, and which rules it is designed to trigger
STAGE_INFO = {
    STAGES[0]: {"name": "Collection", "expected_rules": ["R3", "R4"],
                "description": "Nine feeder accounts pay a mule account opened six days earlier, "
                               "all within 25 minutes."},
    STAGES[1]: {"name": "Consolidation", "expected_rules": ["R1"],
                "description": "The mule forwards almost everything it collected to a collector "
                               "in one large transfer."},
    STAGES[2]: {"name": "Layering", "expected_rules": ["R6"],
                "description": "The collector sends money round a loop through two shell companies "
                               "and back, each hop kept under the Rs 1,00,000 threshold."},
    STAGES[3]: {"name": "Cash-out", "expected_rules": ["R2", "R5"],
                "description": "The collector splits the money into nine transfers just under "
                               "Rs 1,00,000 to nine cash-out accounts within eight minutes."},
}
ACCOUNT_TYPES = {"feeder": "Savings", "mule": "Wallet", "collector": "Current",
                 "shell": "Business", "cash-out": "Savings"}


def scenario_accounts() -> list[dict]:
    """The 22 accounts, as rows for the accounts table."""
    created = {u: BASE - timedelta(days=300 + 37 * i) for i, u in enumerate(FEEDERS)}
    created[MULE] = BASE - timedelta(days=6)            # brand-new account -> R3
    created[COLLECTOR] = BASE - timedelta(days=500)
    created.update({SHELLS[0]: BASE - timedelta(days=200), SHELLS[1]: BASE - timedelta(days=180)})
    created.update({u: BASE - timedelta(days=250 + 23 * i) for i, u in enumerate(CASHOUTS)})
    return [
        dict(account_uid=uid, customer_name=name, email=f"{uid.lower()}@demo.example",
             phone=f"90000{i:05d}", account_type=ACCOUNT_TYPES[ROLES[uid]], created_at=created[uid],
             risk_level="Low", fraud_score=0.0, is_fraud=0, is_active=1)
        for i, (uid, name) in enumerate(zip(ROLES, NAMES))
    ]


def scenario_transactions() -> list[tuple[str, dict]]:
    """The 22 scripted transactions as (stage, transaction row) pairs, in time order."""
    rows = []

    def add(stage, sender, receiver, amount, ts):
        rows.append((stage, dict(
            txn_uid=f"{PREFIX}TXN{len(rows) + 1:03d}", sender_uid=sender, receiver_uid=receiver,
            amount=float(amount), timestamp=ts, txn_type="transfer", status="normal",
            is_fraud=0, fraud_score=0.0,
        )))

    # 1) feeders -> mule within 25 minutes (one under Rs 50,000, so R3 skips it)
    feed_amounts = [52000, 61500, 48000, 75000, 83000, 57500, 66000, 90000, 71000]
    feed_minutes = [0, 3, 5, 8, 11, 14, 17, 21, 25]
    for uid, amt, m in zip(FEEDERS, feed_amounts, feed_minutes):
        add(STAGES[0], uid, MULE, amt, BASE + timedelta(minutes=m))

    # 2) mule forwards ~97% to the collector in one go
    add(STAGES[1], MULE, COLLECTOR, round(sum(feed_amounts) * 0.97, 2), BASE + timedelta(minutes=50))

    # 3) layering loop through two shell companies within 8 hours, under the R1 threshold
    add(STAGES[2], COLLECTOR, SHELLS[0], 92000, BASE + timedelta(hours=3))
    add(STAGES[2], SHELLS[0], SHELLS[1], 90500, BASE + timedelta(hours=5))
    add(STAGES[2], SHELLS[1], COLLECTOR, 89000, BASE + timedelta(hours=8))

    # 4) structured cash-out: 9 transfers just under the Rs 1,00,000 threshold in 8 minutes
    cash_amounts = [99500, 98200, 97800, 99000, 96500, 98900, 97200, 99300, 96800]
    for i, (uid, amt) in enumerate(zip(CASHOUTS, cash_amounts)):
        add(STAGES[3], COLLECTOR, uid, amt, BASE + timedelta(hours=26, minutes=i))
    return rows


def stage_of() -> dict[str, str]:
    """txn_uid -> stage, for the scripted transactions."""
    return {row["txn_uid"]: stage for stage, row in scenario_transactions()}
