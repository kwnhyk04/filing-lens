from datetime import date

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


def test_a_reply_without_other_companies_still_parses() -> None:
    reply = (
        '{"route":"textual","tickers":["aapl"],"fiscal_years":[],'
        '"fiscal_period":null,"metric":null}'
    )
    parsed = router.parse(reply, "groq:openai/gpt-oss-20b")
    assert parsed.tickers == ["AAPL"] and parsed.other_companies == []
    named = routing(other_companies=[" Netflix ", "Netflix", ""])
    assert named.other_companies == ["Netflix"]
