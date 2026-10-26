"""Golden set v1: questions built from the dev database, candidate pools to label, the manifest.

    uv run --env-file .env python -m evals.golden build    # questions.jsonl, pools.jsonl
    uv run python -m evals.golden freeze                    # after labeling: manifest.json

Numeric and comparison gold comes from XBRL facts by the latest-filed rule (get_financial_fact).
Passage gold (textual questions; none for the absent ones) is AI-labeled, spot-checked by a
non-expert (user decision, 2026-10-16): Claude labeled every pooled passage (ai_labels.jsonl);
the user labeled a blind sample and made the final call on each disagreement after seeing
Claude's reason (labels.jsonl, `make audit`), and later corrected two calls (step
"correction"). The final label is the user's where given, otherwise Claude's; see
evals/eval-card.md. Build keeps every record it wrote and adds
missing ones; once freeze has written the manifest, nothing in the version may change: a change
makes v2.
"""

import asyncio
import csv
import hashlib
import json
import os
import random
import sys
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from evals.metrics import bootstrap, cohen_kappa
from filinglens_core.settings import EMBEDDING_MODELS, ApiSettings, EmbeddingColumn, load_settings
from filinglens_db import make_engine
from filinglens_db.models import Section
from filinglens_llm.local import embed
from filinglens_llm.router import METRICS
from filinglens_retrieval import Scope, matching_chunks, nearest_chunks, search
from filinglens_retrieval.facts import Fact, get_financial_fact, latest_fiscal_year
from filinglens_telemetry import configure_logging

VERSION = "v1"
ROOT = Path(__file__).parent / "golden" / VERSION
FILES = ("questions.jsonl", "pools.jsonl", "ai_labels.jsonl", "audit.jsonl", "labels.jsonl")
AI_LABELS, AUDIT, USER_LABELS = (
    ROOT / "ai_labels.jsonl",
    ROOT / "audit.jsonl",
    ROOT / "labels.jsonl",
)
COMPANIES = Path(__file__).parent / "golden-companies.csv"
NAMES = {
    "AAPL": "Apple", "MSFT": "Microsoft", "NVDA": "NVIDIA", "GOOGL": "Alphabet", "META": "Meta",
    "VZ": "Verizon", "AMZN": "Amazon", "TSLA": "Tesla", "HD": "Home Depot", "WMT": "Walmart",
    "PG": "Procter & Gamble", "KO": "Coca-Cola", "COP": "ConocoPhillips", "CVX": "Chevron",
    "JPM": "JPMorgan Chase", "BAC": "Bank of America", "GS": "Goldman Sachs", "V": "Visa",
    "LLY": "Eli Lilly", "UNH": "UnitedHealth Group", "JNJ": "Johnson & Johnson", "PFE": "Pfizer",
    "CAT": "Caterpillar", "LMT": "Lockheed Martin", "UNP": "Union Pacific", "LIN": "Linde",
    "FCX": "Freeport-McMoRan", "PLD": "Prologis", "NEE": "NextEra Energy", "DUK": "Duke Energy",
}  # fmt: skip
ASK = {
    "revenue": "What was {name}'s total revenue in fiscal {year}?",
    "net_income": "What was {name}'s net income in fiscal {year}?",
    "eps_diluted": "What were {name}'s diluted earnings per share in fiscal {year}?",
    "operating_income": "What was {name}'s operating income in fiscal {year}?",
    "gross_profit": "What was {name}'s gross profit in fiscal {year}?",
    "total_assets": "What were {name}'s total assets at the end of fiscal {year}?",
    "total_liabilities": "What were {name}'s total liabilities at the end of fiscal {year}?",
    "cash": "How much cash and cash equivalents did {name} hold at the end of fiscal {year}?",
    "long_term_debt": "How much long-term debt did {name} carry at the end of fiscal {year}?",
    "operating_cash_flow": "How much cash did {name}'s operations provide in fiscal {year}?",
    "capital_expenditures": "How much did {name} spend on capital expenditures in fiscal {year}?",
    "research_and_development": "How much did {name} spend on R&D in fiscal {year}?",
    "dividends_per_share": "What dividends per share did {name} declare in fiscal {year}?",
}
LABELS = {
    "revenue": "total revenue",
    "net_income": "net income",
    "operating_income": "operating income",
    "gross_profit": "gross profit",
    "total_assets": "total assets",
    "operating_cash_flow": "cash from operating activities",
}
# Metrics fitted to each sector: no revenue for banks, and none of the misfit concepts the survey
# of 2026-10-16 found (JNJ R&D 0.1B, PLD dividends 0.03, CAT and FCX net income as ProfitLoss).
NUMERIC = [  # id, ticker, metric, fiscal years before the company's latest
    ("n01", "AAPL", "revenue", 0), ("n02", "MSFT", "net_income", 0),
    ("n03", "NVDA", "revenue", 0), ("n04", "GOOGL", "capital_expenditures", 0),
    ("n05", "META", "research_and_development", 0), ("n06", "VZ", "operating_cash_flow", 0),
    ("n07", "AMZN", "operating_income", 0), ("n08", "TSLA", "gross_profit", 0),
    ("n09", "HD", "eps_diluted", 0), ("n10", "WMT", "revenue", 0),
    ("n11", "PG", "dividends_per_share", 0), ("n12", "KO", "net_income", 0),
    ("n13", "COP", "total_assets", 0), ("n14", "CVX", "revenue", 0),
    ("n15", "JPM", "net_income", 0), ("n16", "BAC", "eps_diluted", 0),
    ("n17", "GS", "total_assets", 0), ("n18", "V", "net_income", 0),
    ("n19", "LLY", "revenue", 0), ("n20", "UNH", "operating_income", 0),
    ("n21", "JNJ", "eps_diluted", 0), ("n22", "PFE", "long_term_debt", 0),
    ("n23", "CAT", "revenue", 0), ("n24", "LMT", "cash", 0),
    ("n25", "UNP", "capital_expenditures", 0), ("n26", "LIN", "operating_income", 0),
    ("n27", "FCX", "revenue", 0), ("n28", "PLD", "total_liabilities", 0),
    ("n29", "NEE", "long_term_debt", 0), ("n30", "DUK", "eps_diluted", 0),
    ("n31", "AAPL", "eps_diluted", 1), ("n32", "MSFT", "revenue", 1),
    ("n33", "NVDA", "net_income", 1), ("n34", "AMZN", "total_assets", 1),
    ("n35", "META", "operating_cash_flow", 1), ("n36", "KO", "operating_income", 1),
    ("n37", "JPM", "total_assets", 1), ("n38", "LLY", "net_income", 1),
    ("n39", "UNP", "net_income", 1), ("n40", "DUK", "capital_expenditures", 1),
]  # fmt: skip
PEERS = [  # id, ticker, ticker, metric, fiscal year
    ("c01", "JPM", "BAC", "net_income", 2025), ("c02", "GOOGL", "META", "revenue", 2025),
    ("c03", "CVX", "COP", "net_income", 2025), ("c04", "LLY", "PFE", "revenue", 2025),
    ("c05", "NEE", "DUK", "total_assets", 2025), ("c06", "CAT", "UNP", "operating_cash_flow", 2025),
    ("c07", "KO", "PG", "revenue", 2025), ("c08", "AMZN", "WMT", "revenue", 2025),
]  # fmt: skip
YEARS = [  # id, ticker, metric: the latest fiscal year against the one before
    ("c09", "AAPL", "revenue"), ("c10", "MSFT", "operating_income"),
    ("c11", "NVDA", "gross_profit"), ("c12", "TSLA", "net_income"),
    ("c13", "UNH", "net_income"), ("c14", "HD", "revenue"), ("c15", "V", "revenue"),
]  # fmt: skip
TEXTUAL = [  # id, ticker, question, fiscal years it names, expected items, keyword hints
    (
        "x01", "AAPL", "Where are the outsourcing partners that manufacture Apple's products?",
        [], ["1A", "1"], ["outsourcing partners", "outside of the U.S.", "China mainland"],
    ),
    (
        "x02", "NVDA", "How do U.S. export controls affect NVIDIA's sales to China?",
        [], ["1A", "1", "7"], ["export controls", "license requirement", "H20", "China"],
    ),
    (
        "x03", "GOOGL", "What does Alphabet say about its reliance on advertising for revenue?",
        [], ["1A", "1", "7"], ["advertising revenues", "significant portion", "advertisers"],
    ),
    (
        "x04", "AMZN", "What are Amazon's reportable segments?",
        [], ["8", "7", "1"], ["reportable segments", "North America", "International", "AWS"],
    ),
    (
        "x05", "TSLA", "Where are Tesla's main vehicle manufacturing facilities?",
        [], ["2", "1"], ["Gigafactory", "Fremont Factory", "Gigafactory Shanghai", "Berlin"],
    ),
    (
        "x06", "WMT", "What are Walmart's reportable segments?",
        [], ["1", "7", "8"], ["Walmart U.S.", "Walmart International", "Sam's Club U.S."],
    ),
    (
        "x07", "KO", "What does Coca-Cola sell to its bottling partners?",
        [], ["1", "7"], ["concentrates and syrups", "bottling partners", "finished beverages"],
    ),
    (
        "x08", "COP", "What is ConocoPhillips's Willow project in Alaska?",
        [], ["1", "7", "1A"], ["Willow", "Western North Slope", "Bear Tooth Unit", "first oil"],
    ),
    (
        "x09", "CVX", "What does Chevron say about its acquisition of Hess?",
        [], ["1", "16", "1A"], ["Hess", "acquisition", "Stabroek", "Guyana"],
    ),
    (
        "x10", "JPM", "What are JPMorgan Chase's reportable business segments?",
        [], ["1", "15", "16"],
        ["reportable business segments", "Consumer & Community Banking", "Asset & Wealth"],
    ),
    (
        "x11", "V", "What does Visa say about the interchange multidistrict litigation?",
        [], ["7", "8", "3", "1A"], ["interchange multidistrict litigation", "MDL 1720", "escrow"],
    ),
    (
        "x12", "LLY", "Which products drove Eli Lilly's revenue growth in 2025?",
        [2025], ["7", "1"], ["Mounjaro", "Zepbound", "volume increase", "revenue increased"],
    ),
    (
        "x13", "UNH", "Which businesses make up UnitedHealth Group?",
        [], ["1", "7"], ["UnitedHealthcare", "Optum Health", "Optum Insight", "Optum Rx"],
    ),
    (
        "x14", "PFE", "When do the basic product patents of Pfizer's most significant products "
        "expire?", [], ["1", "7", "1A"], ["basic product patent", "patent rights", "expires"],
    ),
    (
        "x15", "CAT", "How large was Caterpillar's order backlog at the end of 2025?",
        [2025], ["1", "7"], ["order backlog", "backlog believed to be firm", "dealer inventory"],
    ),
    (
        "x16", "LMT", "How much of Lockheed Martin's net sales came from the U.S. Government?",
        [], ["1", "7", "1A"], ["U.S. Government", "consolidated net sales", "foreign military"],
    ),
    (
        "x17", "UNP", "What does Union Pacific say about its planned merger with Norfolk Southern?",
        [], ["1", "1A", "7"], ["Norfolk Southern", "merger", "Surface Transportation Board"],
    ),
    (
        "x18", "FCX", "What happened at Freeport-McMoRan's Grasberg mine in September 2025?",
        [2025], ["1", "7", "1A"], ["mud rush", "Grasberg Block Cave", "September 2025"],
    ),
    (
        "x19", "PLD", "How does Prologis describe its strategic capital business?",
        [], ["1", "16", "7"], ["Strategic Capital", "co-investment ventures", "third-party"],
    ),
    (
        "x20", "DUK", "Which states do Duke Energy's electric utilities serve?",
        [], ["1", "2"], ["service territory", "North Carolina", "Florida", "Indiana", "Kentucky"],
    ),
]  # fmt: skip
ABSENT = [  # id, ticker, question, fiscal years, items, hints: in scope, but not in the filing
    (
        "a01", "AAPL", "How much revenue did Apple's Vision Pro headset generate in fiscal 2025?",
        [2025], ["1", "7", "8"], ["Vision Pro", "Wearables, Home and Accessories"],
    ),
    (
        "a02", "TSLA", "How many vehicles did Tesla deliver in Germany in 2025?",
        [2025], ["1", "7"], ["deliveries", "Germany", "vehicles delivered"],
    ),
    (
        "a03", "MSFT", "What was Microsoft CEO Satya Nadella's total compensation for fiscal 2026?",
        [2026], ["1", "11"], ["Nadella", "executive compensation", "Chief Executive Officer"],
    ),
    (
        "a04", "KO", "How much revenue did the Sprite brand generate for Coca-Cola in 2025?",
        [2025], ["1", "7"], ["Sprite", "unit case volume", "net operating revenues"],
    ),
    (
        "a05", "WMT", "How many people does Walmart employ in Texas?",
        [], ["1", "2"], ["associates", "Texas", "employees"],
    ),
    (
        "a06", "JPM", "What interest rate does JPMorgan Chase charge on its Sapphire credit cards?",
        [], ["1", "15"], ["Sapphire", "credit card", "annual percentage rate"],
    ),
    (
        "a07", "LLY", "How many patients in Germany were treated with Mounjaro in 2025?",
        [2025], ["1", "7"], ["Mounjaro", "Germany", "patients"],
    ),
    (
        "a08", "AMZN", "How much electricity did Amazon's data centers in Virginia use in 2025?",
        [2025], ["1", "2", "7"], ["data centers", "Virginia", "electricity"],
    ),
    (
        "a09", "CAT", "How many Caterpillar dealers are located in Brazil?",
        [], ["1", "2"], ["dealers", "Brazil", "dealer network"],
    ),
    (
        "a10", "UNP", "What was Union Pacific's average train speed in March 2025?",
        [2025], ["7", "1"], ["average train speed", "freight car velocity", "March"],
    ),
]  # fmt: skip
OUT_OF_SCOPE = [  # id, question, tickers
    ("o01", "Will NVIDIA's stock price go up next year?", ["NVDA"]),
    ("o02", "Should I buy Tesla shares this month?", ["TSLA"]),
    ("o03", "Who won the 2026 FIFA World Cup?", []),
]
UNTRACKED = [  # id, question, route, tickers, fiscal years, metric
    ("u01", "What was Netflix's revenue in fiscal 2025?", "numeric", ["NFLX"], [2025], "revenue"),
    ("u02", "What risks does Costco describe in its latest annual report?", "textual", ["COST"],
     [], None),
]  # fmt: skip
# Time traps ask for the fiscal year after the company's latest 10-K. Apple and Visa are left
# out: their next 10-Ks (late October and November 2026) would make the traps answerable.
TRAPS_NUMERIC = [  # id, ticker, metric
    ("t01", "TSLA", "revenue"), ("t02", "AMZN", "net_income"), ("t03", "JPM", "eps_diluted"),
    ("t04", "LLY", "revenue"), ("t05", "NEE", "total_assets"), ("t06", "MSFT", "revenue"),
]  # fmt: skip
TRAPS_TEXTUAL = [  # id, ticker, question with {year}
    ("t07", "CVX", "What risks did Chevron describe in its fiscal {year} annual report?"),
    ("t08", "CAT", "What did Caterpillar say about its order backlog in its fiscal {year} 10-K?"),
    ("t09", "NVDA", "How did export controls affect NVIDIA in fiscal {year}, per its 10-K?"),
    ("t10", "WMT", "What did Walmart say about e-commerce growth in its fiscal {year} 10-K?"),
]
# Golden v2's test questions (user's plan, 2026-10-26): written in free phrasing before the fixes of
# that round, and never used to tune them; their hash is in docs/activity-log.md. v1's 100
# questions all go to v2's dev split. Facts checked against the dev database when written.
V2_NUMERIC = [  # id, ticker, metric, fiscal year, question
    ("n41", "V", "net_income", 2025, "How much did Visa earn in fiscal 2025?"),
    ("n42", "HD", "revenue", 2025, "What were Home Depot's net sales for fiscal 2025?"),
    ("n43", "PG", "operating_income", 2026,
     "What operating income did Procter & Gamble report in its fiscal 2026 results?"),
    ("n44", "KO", "eps_diluted", 2025, "What were Coca-Cola's diluted earnings per share in 2025?"),
    ("n45", "UNP", "revenue", 2025, "How much revenue did Union Pacific bring in during 2025?"),
    ("n46", "LIN", "total_assets", 2025,
     "What did Linde's balance sheet show for total assets at the end of 2025?"),
    ("n47", "GOOGL", "net_income", 2024, "How much did Alphabet earn in 2024?"),
    ("n48", "TSLA", "operating_cash_flow", 2025,
     "How much cash did Tesla generate from its operating activities in 2025?"),
    ("n49", "NEE", "net_income", 2025, "What was NextEra Energy's profit for 2025?"),
    ("n50", "MSFT", "research_and_development", 2026,
     "How much did Microsoft put into research and development in fiscal 2026?"),
    ("n51", "GS", "eps_diluted", 2025, "What diluted EPS did Goldman Sachs post for 2025?"),
    ("n52", "WMT", "capital_expenditures", 2026,
     "What did Walmart spend on property and equipment in fiscal 2026?"),
]  # fmt: skip
V2_PEERS = [  # id, ticker, ticker, metric, fiscal year, question
    ("c16", "CVX", "COP", "revenue", 2025,
     "Did Chevron or ConocoPhillips bring in more revenue in 2025?"),
    ("c17", "BAC", "GS", "total_assets", 2025,
     "Which bank had the larger balance sheet at the end of 2025, Bank of America or Goldman"
     " Sachs?"),
    ("c18", "PFE", "JNJ", "net_income", 2025,
     "Was Pfizer's or Johnson & Johnson's net income bigger in 2025?"),
    ("c19", "CAT", "UNP", "capital_expenditures", 2025,
     "Between Caterpillar and Union Pacific, which spent more on capital expenditures in 2025?"),
]  # fmt: skip
V2_YEARS = [  # id, ticker, metric, fiscal year (compared with the year before), question
    ("c20", "GOOGL", "revenue", 2025, "Did Alphabet's revenue grow in 2025 compared with 2024?"),
    ("c21", "WMT", "operating_income", 2026,
     "How did Walmart's operating income change from fiscal 2025 to fiscal 2026?"),
    ("c22", "DUK", "net_income", 2025, "Was Duke Energy's net income higher in 2025 than in 2024?"),
    ("c23", "META", "research_and_development", 2025,
     "By how much did Meta's research and development spending change between 2024 and 2025?"),
]  # fmt: skip
V2_TEXTUAL = [  # id, ticker, question, fiscal years it names, expected items, keyword hints
    (
        "x21", "AAPL", "How does Apple describe the competition it faces in smartphones?",
        [], ["1", "1A"], ["competition", "smartphone", "aggressive price competition"],
    ),
    (
        "x22", "MSFT", "What does Microsoft say about its investment in OpenAI?",
        [], ["1", "7", "8", "1A"], ["OpenAI", "investment", "equity method"],
    ),
    (
        "x23", "NVDA", "Do a few customers account for a large share of NVIDIA's revenue?",
        [], ["1A", "8", "7"], ["direct customer", "customer concentration", "of total revenue"],
    ),
    (
        "x24", "META", "What does Meta say about the losses in Reality Labs?",
        [], ["7", "1A", "1"], ["Reality Labs", "operating losses", "metaverse"],
    ),
    (
        "x25", "VZ", "How is Verizon growing its fixed wireless access business?",
        [], ["1", "7"], ["fixed wireless access", "broadband", "subscribers"],
    ),
    (
        "x26", "AMZN", "What is Amazon spending on infrastructure for artificial intelligence?",
        [], ["7", "1A", "1"], ["capital expenditures", "artificial intelligence", "data centers"],
    ),
    (
        "x27", "TSLA", "What are Tesla's regulatory credits and who buys them?",
        [], ["7", "8", "1"], ["regulatory credits", "other automakers", "automotive regulatory"],
    ),
    (
        "x28", "HD", "How does Home Depot describe its SRS Distribution business?",
        [], ["1", "7", "8"], ["SRS", "specialty trade distribution", "Pro customers"],
    ),
    (
        "x29", "PG", "Which product categories make up Procter & Gamble's segments?",
        [], ["1", "8"], ["Fabric & Home Care", "Beauty", "Grooming", "Health Care"],
    ),
    (
        "x30", "KO", "How do currency exchange rates affect Coca-Cola's results?",
        [], ["7", "7A", "1A"], ["foreign currency exchange rate", "U.S. dollar", "unfavorable"],
    ),
    (
        "x31", "COP", "What did ConocoPhillips gain from buying Marathon Oil?",
        [], ["1", "7", "8"], ["Marathon Oil", "acquisition", "completed"],
    ),
    (
        "x32", "CVX", "What does Chevron say about its business in Venezuela?",
        [], ["1", "7", "8", "14"], ["Venezuela", "Petropiar", "license"],
    ),
    (
        "x33", "JPM", "How does JPMorgan Chase manage its liquidity risk?",
        [], ["7", "1A", "15"], ["liquidity risk", "LCR", "HQLA"],
    ),
    (
        "x34", "BAC", "How is Bank of America organized into business segments?",
        [], ["1", "7", "8"], ["Consumer Banking", "Global Wealth & Investment Management",
                              "Global Banking", "Global Markets"],
    ),
    (
        "x35", "GS", "What has Goldman Sachs said about winding down its consumer business?",
        [], ["1", "7", "8"], ["Apple Card", "consumer", "Platform Solutions"],
    ),
    (
        "x36", "V", "How does Visa earn revenue from cross-border payments?",
        [], ["1", "7"], ["international transaction revenues", "cross-border", "currency"],
    ),
    (
        "x37", "LLY", "What is Eli Lilly doing to expand manufacturing for its incretin medicines?",
        [], ["1", "7", "1A"], ["manufacturing capacity", "incretin", "facilities"],
    ),
    (
        "x38", "UNH", "What did UnitedHealth Group say about medical cost trends in 2025?",
        [2025], ["7", "1A"], ["medical cost trend", "medical care ratio", "elevated"],
    ),
    (
        "x39", "JNJ", "Where does Johnson & Johnson's talc litigation stand?",
        [], ["8", "1A", "3"], ["talc", "Red River Talc", "ovarian cancer"],
    ),
    (
        "x40", "PFE", "What does Pfizer say about the Seagen acquisition?",
        [], ["1", "7", "8"], ["Seagen", "acquisition", "oncology"],
    ),
    (
        "x41", "CAT", "How does Caterpillar sell through its dealers?",
        [], ["1", "1A"], ["dealers", "independently owned", "distribution"],
    ),
    (
        "x42", "LMT", "Which programs make up Lockheed Martin's Aeronautics business?",
        [], ["1", "7"], ["F-35", "Aeronautics", "F-16", "C-130"],
    ),
    (
        "x43", "LIN", "How does Linde deliver industrial gases to its customers?",
        [], ["1"], ["on-site", "merchant", "packaged gases", "distribution"],
    ),
    (
        "x44", "PLD", "How large is Prologis' portfolio of logistics space?",
        [], ["1", "2"], ["square feet", "operating portfolio", "owned and managed"],
    ),
    (
        "x45", "NEE", "What are NextEra Energy's main businesses?",
        [], ["1", "7"], ["FPL", "NEER", "Florida Power & Light", "NextEra Energy Resources"],
    ),
]  # fmt: skip
V2_ABSENT = [  # id, ticker, question, fiscal years, items, hints: in scope, but not in the filing
    (
        "a11", "NVDA", "How many GPUs did NVIDIA ship to Microsoft in fiscal 2026?",
        [2026], ["1", "7"], ["Microsoft", "units shipped", "GPUs"],
    ),
    (
        "a12", "HD", "How many people work at Home Depot's Atlanta headquarters?",
        [], ["1", "2"], ["Atlanta", "headquarters", "associates"],
    ),
    (
        "a13", "PFE", "What price does Pfizer charge for Paxlovid in Japan?",
        [], ["1", "7"], ["Paxlovid", "Japan", "price"],
    ),
    (
        "a14", "DUK", "How many electric vehicles are in Duke Energy's own fleet?",
        [], ["1", "7"], ["electric vehicles", "fleet", "vehicles"],
    ),
]  # fmt: skip
V2_OUT_OF_SCOPE = [  # id, question, tickers
    ("o04", "Is Microsoft a good long-term investment?", ["MSFT"]),
    ("o05", "What will Amazon's share price be at the end of 2026?", ["AMZN"]),
    ("o06", "Which Visa card has the best travel rewards?", ["V"]),
]
V2_UNTRACKED = [  # id, question, route, tickers, fiscal years, metric
    ("u03", "What was Oracle's net income in fiscal 2025?", "numeric", ["ORCL"], [2025],
     "net_income"),
]  # fmt: skip
V2_TRAPS = [  # id, ticker, route, metric, fiscal year (after the latest 10-K), question
    ("t11", "NEE", "numeric", "revenue", 2026,
     "What did NextEra Energy report as total revenue for fiscal 2026?"),
    ("t12", "PG", "textual", None, 2027,
     "What did Procter & Gamble say about pricing in its fiscal 2027 annual report?"),
]  # fmt: skip
# Questions per (category, kind) in dev (the rest are test), and in the ci subset (from dev).
DEV = {
    ("numeric", "latest"): 21, ("numeric", "prior"): 7, ("textual", "passage"): 14,
    ("comparison", "peers"): 5, ("comparison", "years"): 5, ("unanswerable", "absent"): 7,
    ("unanswerable", "out_of_scope"): 2, ("unanswerable", "untracked"): 2,
    ("time_trap", "numeric"): 4, ("time_trap", "textual"): 3,
}  # fmt: skip
CI = {
    ("numeric", "latest"): 6, ("numeric", "prior"): 2, ("textual", "passage"): 4,
    ("comparison", "peers"): 2, ("comparison", "years"): 1, ("unanswerable", "absent"): 1,
    ("unanswerable", "out_of_scope"): 1, ("unanswerable", "untracked"): 1,
    ("time_trap", "numeric"): 1, ("time_trap", "textual"): 1,
}  # fmt: skip
# The reranker configurations decision 1 compares (model, candidates, max tokens); each feeds the
# pools, so recall is fair to all three.
RERANKERS = {
    "tinybert-50": ("cross-encoder/ms-marco-TinyBERT-L-2-v2", 50, 512),
    "minilm2-24": ("cross-encoder/ms-marco-MiniLM-L-2-v2", 24, 256),
    "minilm6-100": ("cross-encoder/ms-marco-MiniLM-L-6-v2", 100, 512),
}
POOL_TIMEOUT_S = 60.0  # never degraded: a pool must hold each reranker's real top
# Chunks added to a pool after a pooling miss: those of the question's company holding a phrase.
# x15: no source caught CAT's Item 1 "Order Backlog" paragraph ($51.2 billion at December 31,
# 2025); the AI labels then gave x15 no gold (2026-10-16, user decision to keep x15).
ADDED = {"x15": ["order backlog"]}
PHRASE_CHUNKS = text(
    """
    select c.id from chunks c
    join sections s on s.id = c.section_id
    join filings f on f.id = s.filing_id
    where f.status = 'indexed' and f.cik = any(:ciks)
      and c.tsv @@ phraseto_tsquery('english', :phrase)
    """
)
PHRASE_HITS = text(
    """
    select c.id from chunks c
    join sections s on s.id = c.section_id
    join filings f on f.id = s.filing_id
    where f.status = 'indexed' and f.cik = any(:ciks)
      and c.tsv @@ websearch_to_tsquery('english', :hints)
    order by ts_rank_cd(c.tsv, websearch_to_tsquery('english', :hints)) desc, c.id
    limit 5
    """
)
CANDIDATES = text(
    """
    select c.id, c.text, c.char_start, s.item, f.accession_number, f.cik from chunks c
    join sections s on s.id = c.section_id
    join filings f on f.id = s.filing_id
    where c.id = any(:ids)
    """
)


def sha256(path: Path) -> str:
    """Of the file with LF line ends, so a CRLF checkout hashes the same."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    lines = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    path.write_text(lines, encoding="utf-8", newline="\n")


def read_manifest() -> dict[str, Any]:
    return json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))


def write_manifest(manifest: dict[str, Any]) -> None:
    body = json.dumps(manifest, indent=1, ensure_ascii=False) + "\n"
    (ROOT / "manifest.json").write_text(body, encoding="utf-8", newline="\n")


def companies() -> dict[str, int]:
    """CIK by ticker for the 30 golden-set companies."""
    with COMPANIES.open(encoding="utf-8") as file:
        return {row["ticker"]: int(row["cik"]) for row in csv.DictReader(file)}


def labels(rows: list[dict[str, Any]]) -> tuple[dict[tuple[str, str], bool], set[str]]:
    """The latest label per (question, chunk), and the questions flagged as bad."""
    judged: dict[tuple[str, str], bool] = {}
    flagged: set[str] = set()
    for row in rows:
        if "flag" in row:
            (flagged.add if row["flag"] else flagged.discard)(row["id"])
        else:
            judged[row["id"], row["chunk_id"]] = row["gold"]
    return judged, flagged


def final_labels() -> tuple[dict[tuple[str, str], bool], set[str]]:
    """Gold per (question, chunk): the user's latest label where given, otherwise Claude's."""
    return labels(read_jsonl(AI_LABELS) + read_jsonl(USER_LABELS))


def blind_labels(rows: list[dict[str, Any]]) -> dict[tuple[str, str], bool]:
    """The user's latest blind label per (question, chunk): rows without a review or
    correction step."""
    return labels([row for row in rows if "step" not in row])[0]


def audit_stats() -> dict[str, Any]:
    """The user's blind labels against Claude's, before review; how the review went; and the
    corrections the user made later, after reading the passage text."""
    claude = labels(read_jsonl(AI_LABELS))[0]
    rows = read_jsonl(USER_LABELS)
    mine = blind_labels(rows)
    pairs = [(mine[key], claude[key]) for key in mine if key in claude]
    differ = [key for key in mine if key in claude and mine[key] != claude[key]]
    if not pairs:
        raise SystemExit("No blind labels yet: run make audit.")
    final = labels(rows)[0]
    review = labels([row for row in rows if row.get("step") == "review"])[0]
    corrected = labels([row for row in rows if row.get("step") == "correction"])[0]
    low, high = bootstrap(pairs, cohen_kappa)
    return {
        "passages": len(pairs),
        "claude_gold": sum(b for _, b in pairs),
        "human_gold": sum(a for a, _ in pairs),
        "agreement": sum(a == b for a, b in pairs) / len(pairs),
        "kappa": cohen_kappa(pairs),
        "kappa_ci": [low, high],
        "disagreements": len(differ),
        "reviewed": sum(key in review for key in differ),
        "review_as_claude": sum(key in review and review[key] == claude[key] for key in differ),
        "corrections": len(corrected),
        "final_as_claude": sum(final[key] == claude[key] for key in differ),
    }


def _fact(ticker: str, fact: Fact) -> dict[str, Any]:
    return {
        "id": fact.id,
        "ticker": ticker,
        "cik": fact.cik,
        "concept": fact.concept,
        "unit": fact.unit,
        "value": str(fact.value),
        "fiscal_year": fact.fiscal_year,  # of the filing that reported it
        "fiscal_period": fact.fiscal_period,
        "period_start": fact.period_start.isoformat() if fact.period_start else None,
        "period_end": fact.period_end.isoformat(),
        "accession_number": fact.accession_number,
        "form": fact.form,
        "filed_on": fact.filed_on.isoformat() if fact.filed_on else None,
    }


def _routing(
    route: str | None, tickers: list[str], years: list[int] | None, metric: str | None
) -> dict[str, Any]:
    """The router's expected output; None leaves a field unscored (ambiguous for the question)."""
    return {"route": route, "tickers": sorted(tickers), "fiscal_years": years, "metric": metric}


async def questions(
    connection: AsyncConnection, ciks: dict[str, int], latest: dict[str, int]
) -> list[dict[str, Any]]:
    """Every question with its gold, in a fixed order; ids are stable across builds."""
    rows: list[dict[str, Any]] = []

    def add(qid: str, category: str, kind: str, question: str, **fields: Any) -> None:
        rows.append({"id": qid, "category": category, "kind": kind, "question": question} | fields)

    async def fact(ticker: str, metric: str, year: int) -> dict[str, Any]:
        unit, concepts = METRICS[metric]
        found = await get_financial_fact(connection, ciks[ticker], concepts, unit, fiscal_year=year)
        if found is None:
            raise SystemExit(f"No {metric} fact for {ticker} in fiscal {year}: pick another.")
        return _fact(ticker, found)

    for qid, ticker, metric, back in NUMERIC:
        year = latest[ticker] - back
        add(
            qid, "numeric", "prior" if back else "latest",
            ASK[metric].format(name=NAMES[ticker], year=year), expect="answer",
            routing=_routing("numeric", [ticker], [year], metric), ciks=[ciks[ticker]],
            facts=[await fact(ticker, metric, year)],
        )  # fmt: skip
    for qid, first, second, metric, year in PEERS:
        question = (
            f"Which was higher in fiscal {year}: {NAMES[first]}'s or {NAMES[second]}'s"
            f" {LABELS[metric]}?"
        )
        add(
            qid, "comparison", "peers", question, expect="answer",
            routing=_routing("comparison", [first, second], [year], metric),
            ciks=[ciks[first], ciks[second]],
            facts=[await fact(first, metric, year), await fact(second, metric, year)],
        )  # fmt: skip
    for qid, ticker, metric in YEARS:
        year = latest[ticker]
        question = (
            f"How did {NAMES[ticker]}'s {LABELS[metric]} in fiscal {year} compare with"
            f" fiscal {year - 1}?"
        )
        add(
            qid, "comparison", "years", question, expect="answer",
            routing=_routing("comparison", [ticker], [year - 1, year], metric),
            ciks=[ciks[ticker]],
            facts=[await fact(ticker, metric, year), await fact(ticker, metric, year - 1)],
        )  # fmt: skip
    for qid, ticker, question, years, items, hints in TEXTUAL:
        add(
            qid, "textual", "passage", question, expect="answer",
            routing=_routing("textual", [ticker], years, None), ciks=[ciks[ticker]],
            fiscal_years=years, items=items, keywords=hints,
        )  # fmt: skip
    for qid, ticker, question, years, items, hints in ABSENT:
        add(
            qid, "unanswerable", "absent", question, expect="refuse",
            routing=_routing(None, [ticker], None, None), ciks=[ciks[ticker]],
            fiscal_years=years, items=items, keywords=hints,
        )  # fmt: skip
    for qid, question, tickers in OUT_OF_SCOPE:
        add(
            qid, "unanswerable", "out_of_scope", question, expect="refuse",
            routing=_routing("out_of_scope", tickers, None, None),
        )  # fmt: skip
    for qid, question, route, tickers, years, metric in UNTRACKED:
        add(
            qid, "unanswerable", "untracked", question, expect="refuse",
            routing=_routing(route, tickers, years, metric),
        )  # fmt: skip
    for qid, ticker, metric in TRAPS_NUMERIC:
        year = latest[ticker] + 1
        add(
            qid, "time_trap", "numeric", ASK[metric].format(name=NAMES[ticker], year=year),
            expect="refuse", routing=_routing("numeric", [ticker], [year], metric),
            ciks=[ciks[ticker]],
        )  # fmt: skip
    for qid, ticker, template in TRAPS_TEXTUAL:
        year = latest[ticker] + 1
        add(
            qid, "time_trap", "textual", template.format(year=year), expect="refuse",
            routing=_routing("textual", [ticker], [year], None), ciks=[ciks[ticker]],
        )  # fmt: skip
    return rows


def assign_splits(rows: list[dict[str, Any]]) -> None:
    """Dev, test and the ci subset per (category, kind), by position under a fixed seed, so a
    question replaced before the freeze takes its predecessor's split."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault((row["category"], row["kind"]), []).append(row)
    for group, members in groups.items():
        order = list(range(len(members)))
        random.Random(f"{VERSION}:{group[0]}:{group[1]}").shuffle(order)  # noqa: S311 - a split
        for rank, index in enumerate(order):
            members[index]["split"] = "dev" if rank < DEV[group] else "test"
            members[index]["ci"] = rank < CI[group]


async def pool(
    engine: AsyncEngine, column: EmbeddingColumn, question: dict[str, Any]
) -> dict[str, Any]:
    """Candidates for a textual or absent question, shuffled, with no rank or source shown.

    Each reranker configuration's top 10 (top 5 for an absent question) and the hint phrases'
    top 5; for a textual question also the top 5 by vector, by any word of the question and its
    hints, and the same two within the expected item sections: more than the system's own top.
    """
    q, ciks = question["question"], question["ciks"]
    textual = question["category"] == "textual"
    scope = Scope(ciks, question["fiscal_years"] or None)
    found: dict[str, set[str]] = {}

    def keep(source: str, ids: list[str]) -> None:
        for chunk_id in ids:
            found.setdefault(chunk_id, set()).add(source)

    for name, (model, candidates, max_tokens) in RERANKERS.items():
        ranking = await search(
            engine, q, embedding=column, scope=scope, rerank_model=model,
            candidates=candidates, max_tokens=max_tokens, timeout_s=POOL_TIMEOUT_S,
        )  # fmt: skip
        if ranking.degraded:
            raise SystemExit(f"{name} degraded on {question['id']}: the pool would miss its top.")
        keep(name, [hit.chunk_id for hit in ranking.hits[: 10 if textual else 5]])
    hints = " or ".join(f'"{hint}"' for hint in question["keywords"])
    in_items = Section.item.in_(question["items"])
    async with engine.begin() as connection:
        rows = await connection.execute(PHRASE_HITS, {"ciks": ciks, "hints": hints})
        keep("phrases", [row.id for row in rows])
        if textual:
            [vector] = embed([q], EMBEDDING_MODELS[column], query=True)
            # The HNSW scan keeps going past rows the scope filters out (as search does).
            await connection.execute(text("SET LOCAL hnsw.ef_search = 100"))
            await connection.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
            nearest = nearest_chunks(vector, 5, column, scope)
            keep("vector", [row.id for row in await connection.execute(nearest)])
            near = nearest_chunks(vector, 5, column, scope).where(in_items)
            keep("section_vector", [row.id for row in await connection.execute(near)])
            words = " ".join([q, *question["keywords"]])
            matches = await connection.execute(matching_chunks(words, 5, scope))
            keep("words", [row.id for row in matches])
            matches = await connection.execute(matching_chunks(words, 5, scope).where(in_items))
            keep("section_words", [row.id for row in matches])
        candidates = await _candidates(connection, found)
    random.Random(question["id"]).shuffle(candidates)  # noqa: S311 - display order
    return {"id": question["id"], "candidates": candidates}


async def _candidates(
    connection: AsyncConnection, found: dict[str, set[str]]
) -> list[dict[str, Any]]:
    """Pool entries for chunk ids, with the sources that found each, in chunk id order."""
    rows = await connection.execute(CANDIDATES, {"ids": list(found)})
    candidates = [
        {
            "chunk_id": row.id,
            "cik": row.cik,
            "accession_number": row.accession_number,
            "item": row.item,
            "char_start": row.char_start,
            "sha256": hashlib.sha256(row.text.encode()).hexdigest(),
            "found_by": sorted(found[row.id]),
            "text": row.text,
        }
        for row in rows
    ]
    return sorted(candidates, key=lambda candidate: candidate["chunk_id"])


async def add_to_pool(
    engine: AsyncEngine, question: dict[str, Any], pooled: dict[str, Any]
) -> None:
    """Append the chunks of the question's company that hold an ADDED phrase and are missing."""
    have = {candidate["chunk_id"] for candidate in pooled["candidates"]}
    found: dict[str, set[str]] = {}
    async with engine.connect() as connection:
        for phrase in ADDED[question["id"]]:
            rows = await connection.execute(
                PHRASE_CHUNKS, {"ciks": question["ciks"], "phrase": phrase}
            )
            found |= {row.id: {"added"} for row in rows if row.id not in have}
        pooled["candidates"] += await _candidates(connection, found)
    if found:
        print(f"{question['id']}: added {len(found)} candidate(s)", flush=True)


async def build() -> None:
    """Write the questions and pools that are missing; keep every record already written."""
    if (ROOT / "manifest.json").exists() and read_manifest()["status"] == "frozen":
        raise SystemExit(f"Golden set {VERSION} is frozen; a change needs a new version.")
    ROOT.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HUB_OFFLINE", "1")  # pinned models load from HF_HOME, never the Hub
    settings = load_settings(ApiSettings)
    configure_logging("golden", "WARNING")
    engine = make_engine(settings)
    ciks = companies()
    latest: dict[str, int] = {}
    async with engine.connect() as connection:
        for ticker, cik in ciks.items():
            year = await latest_fiscal_year(connection, cik)
            if year is None:
                raise SystemExit(f"{ticker} has no annual facts; run make seed-real first.")
            latest[ticker] = year
        built = await questions(connection, ciks, latest)
    assign_splits(built)
    old = {row["id"]: row for row in read_jsonl(ROOT / "questions.jsonl")}
    rows = [old.get(row["id"], row) for row in built]
    write_jsonl(ROOT / "questions.jsonl", rows)
    pools = {row["id"]: row for row in read_jsonl(ROOT / "pools.jsonl")}
    column = settings.retrieval_embedding_column
    for row in rows:
        if "items" in row and row["id"] not in pools:
            pools[row["id"]] = await pool(engine, column, row)
            print(f"{row['id']}: {len(pools[row['id']]['candidates'])} candidates", flush=True)
        if row["id"] in ADDED:
            await add_to_pool(engine, row, pools[row["id"]])
    write_jsonl(ROOT / "pools.jsonl", [pools[row["id"]] for row in rows if row["id"] in pools])
    await engine.dispose()
    if not (ROOT / "manifest.json").exists():
        corpus = {"embedding_column": column, "latest_fiscal_years": latest}
        as_of = date.today().isoformat()
        write_manifest({"version": VERSION, "status": "draft", "as_of": as_of, "corpus": corpus})
    counts: dict[str, int] = {}
    for row in rows:
        key = f"{row['category']} {row['split']}"
        counts[key] = counts.get(key, 0) + 1
    print(json.dumps(counts, sort_keys=True))
    print(f"{sum(len(p['candidates']) for p in pools.values())} candidates to label")


def freeze() -> None:
    """Check the labels and the audit are complete, then hash every file into the manifest."""
    manifest = read_manifest()
    if manifest["status"] == "frozen":
        raise SystemExit(f"Golden set {VERSION} is already frozen.")
    judged, flagged = final_labels()
    rows = {row["id"]: row for row in read_jsonl(ROOT / "questions.jsonl")}
    problems = [f"{qid}: flagged as a bad question" for qid in sorted(flagged)]
    user = read_jsonl(USER_LABELS)
    mine = blind_labels(user)
    picks = read_jsonl(AUDIT)
    if not picks or any((pick["id"], pick["chunk_id"]) not in mine for pick in picks):
        problems.append("the blind audit sample is not fully labeled (make audit)")
    stats = audit_stats()
    if stats["reviewed"] < stats["disagreements"]:
        problems.append(f"{stats['disagreements'] - stats['reviewed']} disagreements not reviewed")
    for pooled in read_jsonl(ROOT / "pools.jsonl"):
        qid = pooled["id"]
        missing = [c for c in pooled["candidates"] if (qid, c["chunk_id"]) not in judged]
        gold = [c for c in pooled["candidates"] if judged.get((qid, c["chunk_id"]))]
        if missing:
            problems.append(f"{qid}: {len(missing)} candidates not labeled")
        elif rows[qid]["category"] == "textual" and not gold:
            problems.append(f"{qid}: no gold passage, so the question needs replacing")
        elif rows[qid]["category"] == "unanswerable" and gold:
            problems.append(f"{qid}: {len(gold)} passages answer it, so it is not absent")
    if problems:
        raise SystemExit("Not frozen:\n" + "\n".join(problems))
    files = {name: sha256(ROOT / name) for name in FILES}
    manifest |= {
        "status": "frozen",
        "frozen_on": date.today().isoformat(),
        "gold": (
            "AI-labeled (Claude), spot-checked by a non-expert: a fast blind spot-check of a"
            " sample, then a final call on each disagreement after seeing Claude's reason (not"
            " independent), then corrections after reading the passage text; the human's final"
            " label wins where given. The spot-check cannot validate the labels on its own"
        ),
        "audit": stats,
        "files": files,
    }
    write_manifest(manifest)
    print(f"Golden set {VERSION} frozen: {json.dumps(manifest['audit'], indent=1)}")


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "build":
        asyncio.run(build())
    elif command == "freeze":
        freeze()
    else:
        raise SystemExit("usage: python -m evals.golden build|freeze")
