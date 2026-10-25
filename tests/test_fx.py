from procintel import fx

TABLE = {"IDR": {2019: 14000.0, 2020: 14500.0}, "SLL": {2020: 9.83 * 1000}}


def test_usd_passes_through_and_local_converts_at_that_years_rate():
    assert fx.to_usd(1000.0, "USD", 2020, TABLE) == 1000.0
    assert fx.to_usd(14_500_000.0, "IDR", 2020, TABLE) == 1000.0


def test_nearest_year_within_two_years_else_unknown():
    assert fx.to_usd(14_500_000.0, "IDR", 2021, TABLE) == 1000.0     # 2020 is the nearest year with a rate
    assert fx.to_usd(14_500_000.0, "IDR", 2025, TABLE) is None       # 5 years away: not converted
    assert fx.to_usd(1.0, "FKP", 2020, TABLE) is None                # no series at all
    assert fx.to_usd(None, "IDR", 2020, TABLE) is None


def test_issuer_and_redenomination():
    assert fx.issuer("IDR") == "ID" and fx.issuer("EUR") == "EMU" and fx.issuer("XOF") == "SEN"
    # 308,362,500 old leones (a real median SLL award) at 9,830 per USD is about $31k, not $31M
    assert round(fx.to_usd(308_362_500.0, "SLL", 2020, TABLE)) == 31370
