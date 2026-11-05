from datetime import date

import pytest

from filinglens_llm import router

COMPANIES = {"AAPL": "Apple Inc.", "GOOGL": "Alphabet Inc."}


def routing(**fields: object) -> router.Routing:
    base = {"route": "numeric", "tickers": ["AAPL"], "fiscal_years": [2025]}
    return router.Routing.model_validate(
        base | {"fiscal_period": "FY", "metric": "revenue"} | fields
    )


def test_the_schema_limits_tickers_to_the_tracked_companies() -> None:
    schema = router.schema(COMPANIES)
    assert schema["properties"]["tickers"]["items"] == {"type": "string", "enum": ["AAPL", "GOOGL"]}
    assert set(schema["required"]) == set(schema["properties"])  # strict mode: all required
    assert "enum" not in router.schema({})["properties"]["tickers"]["items"]  # none tracked yet


def test_the_prompt_lists_the_tracked_companies() -> None:
    prompt = router.system_prompt(date(2026, 10, 16), COMPANIES)
    assert "AAPL Apple Inc.; GOOGL Alphabet Inc." in prompt
    assert "other_companies" in prompt and "A comparison always" in prompt


def test_problems_name_untracked_tickers_and_a_comparison_without_its_metric() -> None:
    assert router.problems(routing(), COMPANIES) == []
    assert router.problems(routing(tickers=["GOOG"]), COMPANIES) == [
        "tickers GOOG are not on the list; name such companies in other_companies"
    ]
    assert router.problems(routing(route="comparison", metric=None), COMPANIES) == [
        "a comparison needs its metric"
    ]
    assert router.problems(routing(route="textual", metric=None), COMPANIES) == []


def test_other_companies_that_name_a_tracked_one_become_tickers() -> None:
    companies = {
        "KO": "COCA COLA CO",
        "TSLA": "Tesla, Inc.",
        "META": "Meta Platforms, Inc.",
        "PG": "PROCTER & GAMBLE Co",
        "UNP": "UNION PACIFIC CORP",
    }
    named = ["Coca-Cola", "Tesla", "meta", "Procter and Gamble", "Norfolk Southern", "UNP"]
    resolved = router.resolve(routing(tickers=[], other_companies=named), companies)
    assert resolved.tickers == ["KO", "META", "PG", "TSLA", "UNP"]
    assert resolved.other_companies == ["Norfolk Southern"]  # not tracked: stays
    twins = {"AA": "Alpha Energy Inc", "AB": "Alpha Mining Corp"}
    assert router.resolve(routing(tickers=[], other_companies=["Alpha"]), twins).tickers == []


def test_the_guess_reads_named_companies_and_years_from_the_question() -> None:
    companies = COMPANIES | {"KO": "COCA COLA CO", "V": "VISA INC.", "NVDA": "NVIDIA Corporation"}
    guess = router.guess
    assert guess("What did Apple's 10-K for fiscal 2025 say?", companies) == (["AAPL"], [2025])
    assert guess("Compare Coca-Cola and Alphabet in 2024 and 2025", companies) == (
        ["GOOGL", "KO"],
        [2024, 2025],
    )
    assert guess("How does NVDA describe export controls?", companies) == (["NVDA"], [])
    assert guess("What does Visa say about litigation?", companies) == (["V"], [])
    assert guess("Will Netflix's stock go up?", companies) == ([], [])  # not tracked
    assert guess("What is a 10-K?", companies) == ([], [])  # a form name is no year


COMMON_WORDS = {
    "BAC": "BANK OF AMERICA CORP /DE/",
    "HD": "HOME DEPOT, INC.",
    "UNP": "UNION PACIFIC CORP",
    "V": "VISA INC.",
    "META": "Meta Platforms, Inc.",
}


@pytest.mark.parametrize(
    "question",
    [
        "Which bank reported the highest net interest income?",
        "What do union contracts say about strikes?",
        "Do home sales affect revenue?",
        "Which companies mention visa restrictions for workers?",
        "What does the meta-analysis say?",
        # Capitalised only because a sentence opens with it.
        "Bank fees rose at which lenders?",
        "Home prices fell. Union contracts expired. Which filings mention both?",
        "Visa rules changed, so who lost workers?",
        "Meta-analysis of what?",
        "  Home prices fell, so who lost sales?",  # the API keeps a question's spaces
    ],
)
def test_a_common_word_used_normally_names_no_company(question: str) -> None:
    assert router.guess(question, COMMON_WORDS) == ([], [])


@pytest.mark.parametrize(
    ("question", "ticker"),
    [
        ("What was Bank of America's net income?", "BAC"),
        ("Bank of America's net income?", "BAC"),  # the whole name opening the question
        ("Home Depot's revenue?", "HD"),
        ("how did home depot do", "HD"),  # the whole name, in any case
        ("what does union pacific say about strikes", "UNP"),
        ("What does Visa say about litigation?", "V"),
        ("Did Meta's capital spending rise?", "META"),
        ("what did the bank (BAC) report", "BAC"),  # beside its ticker
        ("How does HD describe its stores?", "HD"),
    ],
)
def test_a_common_word_written_as_the_company_names_it(question: str, ticker: str) -> None:
    assert router.guess(question, COMMON_WORDS)[0] == [ticker]


def test_a_second_look_never_tells_the_router_a_common_word_is_a_company() -> None:
    out = routing(route="out_of_scope", tickers=[], fiscal_years=[], metric=None)
    question = "What is the best bank for a home loan?"
    assert router.second_look(out, question, COMMON_WORDS) == []


def test_an_out_of_scope_route_for_a_named_company_gets_a_second_look() -> None:
    """x13, x14 and x18 (test, 2026-10-17) went out of scope with no tickers; o01 and o02, about
    a stock price and buying shares, must stay out of scope without a second call."""
    companies = COMPANIES | {"UNH": "UNITEDHEALTH GROUP INC", "TSLA": "Tesla, Inc."}
    out = routing(route="out_of_scope", tickers=[], fiscal_years=[], metric=None)
    look = router.second_look
    assert look(out, "Which businesses make up UnitedHealth Group?", companies) == ["UNH"]
    assert look(out, "Should I buy Tesla shares this month?", companies) == []
    assert look(out, "Will Apple's stock price go up next year?", companies) == []
    assert look(out, "Who won the 2026 FIFA World Cup?", companies) == []  # names no company
    assert look(routing(), "What was Apple's total revenue in fiscal 2025?", companies) == []
    prompt = router.second_look_prompt("Which businesses make up UnitedHealth Group?", ["UNH"])
    assert prompt.startswith("Which businesses make up UnitedHealth Group?\n")
    assert "UNH" in prompt and "broke the rules" not in prompt


def test_the_plan_takes_the_one_named_company_only_when_the_router_named_none() -> None:
    blank = routing(route="textual", tickers=[], metric=None)
    assert router.fill(blank, ["AAPL"]).tickers == ["AAPL"]
    assert router.fill(blank, ["AAPL", "GOOGL"]).tickers == []  # two named: no guess to take
    # "Bank of New York Mellon" reads as BAC by its first word; the router named it untracked.
    other = blank.model_copy(update={"other_companies": ["Bank of New York Mellon"]})
    assert router.fill(other, ["BAC"]).tickers == []
    out = routing(route="out_of_scope", tickers=[], metric=None)
    assert router.fill(out, ["AAPL"]).tickers == []
    assert router.fill(routing(tickers=["GOOGL"]), ["AAPL"]).tickers == ["GOOGL"]


def test_a_fiscal_year_is_a_filing_year_only_where_the_question_ties_it_to_a_filing() -> None:
    read = router.filing_years
    assert read("What risks did Chevron describe in its fiscal 2026 annual report?") == [2026]
    assert read("What did Caterpillar say about its backlog in its fiscal 2026 10-K?") == [2026]
    assert read("What did Walmart say about e-commerce in its FY2027 10-K?") == [2027]
    assert read("What does its fiscal year 2027 Form 10-K say?") == [2027]
    assert read("What does the 10-K for fiscal 2027 say?") == [2027]
    assert read("What did its annual report for FY 2027 say?") == [2027]
    # A period asked about, which an earlier 10-K may speak of (review finding 3).
    assert read("What purchase obligations are due in fiscal 2027?") == []
    assert read("What risks does Apple see for fiscal 2026?") == []
    assert read("How does its fiscal 2027 capital spending plan look?") == []
    assert read("What did its fiscal 2025 10-K say about fiscal 2027?") == [2025]
    assert read("What did its fiscal 2027 10-Q say?") == []  # a quarter can precede its 10-K
    assert read("What happened at the Grasberg mine in September 2025?") == []
    assert read("What are Apple's 2030 goals?") == []


def test_a_reply_without_other_companies_still_parses() -> None:
    reply = (
        '{"route":"textual","tickers":["aapl"],"fiscal_years":[],'
        '"fiscal_period":null,"metric":null}'
    )
    parsed = router.parse(reply, "groq:openai/gpt-oss-20b")
    assert parsed.tickers == ["AAPL"] and parsed.other_companies == []
    named = routing(other_companies=[" Netflix ", "Netflix", ""])
    assert named.other_companies == ["Netflix"]
