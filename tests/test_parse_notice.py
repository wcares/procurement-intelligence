from procintel import parse_notice as P

def test_supplier_name_with_parentheses_is_kept_whole():
    t = "Awarded Bidder(s): | ABC (INDIA) LTD (12345) | Country: India | Bid Price at Opening | INR"
    assert P.suppliers(t) == [("ABC (INDIA) LTD", 12345)]

def test_multiple_suppliers_and_dedup():
    t = ("Awarded Bidder(s): | POSTHAC S.A (1131603) | .- | Country: Argentina | "
         "ADRA SRL (1131598) | . | Country: Argentina | POSTHAC S.A (1131603) | Evaluated Bid Price | ARS 1")
    assert [f for _, f in P.suppliers(t)] == [1131603, 1131598]

def test_individual_consultant_without_firm_id_yields_nothing():
    assert P.suppliers("Awarded Firm(s): | Individual Consultant | Country: Argentina | Scores | Rank: | 95") == []

def test_award_date_both_labels():
    assert str(P.award_date("Date Notification of Award Issued | (YYYY/MM/DD) | 2025/03/31 |")) == "2025-03-31"
    assert str(P.award_date("Contract Signature Date | (YYYY/MM/DD) | 2020/06/01 |")) == "2020-06-01"

def test_price_prefers_usd():
    assert P.signed_price("Signed Contract price | USD 953944.91; ARS 170134294.86") == ("USD", 953944.91)
    assert P.signed_price("Signed Contract Price | ARS 8202600.00 | Price:") == ("ARS", 8202600.0)

def test_duration_units():
    assert P.duration_days("Duration of Contract | 90 Day(s)") == 90
    assert P.duration_days("Duration of Contract | 2 Month(s)") == 60
