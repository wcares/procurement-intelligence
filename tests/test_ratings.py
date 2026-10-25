from procintel import ratings

# Layouts copied from real ICR data sheets (40130697, 40130174, 40109568, 40120020).
INLINE = ("RATINGS SUMMARY\nOutcome Bank Performance M&E Quality\nSatisfactory Moderately Satisfactory Substantial\n"
          "ISR RATINGS\nNo. Date ISR Archived DO Rating IP Rating\nActual Disbursements\n(US$M)\n"
          "01 24-Nov-2020 Satisfactory Satisfactory 0.00\n02 18-May-2021 Moderately Satisfactory Moderately Satisfactory 0.00\n"
          "@#&OPS~Doctype~OPS^dynamics@icrsectortheme#doctemplate\nSECTORS AND THEMES\n")


def test_outcome_and_inline_isr_rows():
    p = ratings.parse(INLINE)
    assert p["outcome"] == "Satisfactory"
    assert [r[:2] for r in p["isr"]] == [("01", "24-Nov-2020"), ("02", "18-May-2021")]
    assert p["isr"][1][2] == ("Moderately Satisfactory",)  # not read as plain "Satisfactory"
    assert ratings.check(p)["conflict"] is False


def test_outcome_after_page_furniture_is_still_found():
    text = ("RATINGS SUMMARY Outcome Bank Performance M&E Quality ii Official Use Only The World Bank Morocco - "
            "Community-Based Rural Roads Maintenance (P165411) ICR DOCUMENT Moderately Unsatisfactory Moderately "
            "Satisfactory Modest ISR RATINGS No. Date ISR Archived DO Rating IP Rating (US$M) "
            "01 26-Aug-2025 Moderately Satisfactory Moderately Satisfactory 3.10 SECTORS AND THEMES")
    c = ratings.check(ratings.parse(text))
    assert c["outcome"] == "Moderately Unsatisfactory" and c["conflict"] is True and "26-Aug-2025" in c["note"]


def test_wrapped_rows_are_read_and_an_ambiguous_last_row_must_conflict_both_ways():
    # 40109568: rows 07+ wrap one cell; the true last DO is Moderately Unsatisfactory, not row 06's Satisfactory
    text = ("RATINGS SUMMARY Outcome Bank Performance M&E Quality Unsatisfactory Moderately Satisfactory Substantial "
            "ISR RATINGS No. Date ISR Archived DO Rating IP Rating (US$M) "
            "06 04-Jan-2022 Satisfactory Moderately Satisfactory 28.00 "
            "Moderately 07 11-Oct-2022 Moderately Satisfactory 28.00 Unsatisfactory "
            "Moderately 15 31-Jul-2025 Moderately Unsatisfactory 28.00 Unsatisfactory SECTORS AND THEMES")
    p = ratings.parse(text)
    assert [r[0] for r in p["isr"]] == ["06", "07", "15"]
    assert p["isr"][1][2] == ("Moderately Satisfactory", "Moderately Unsatisfactory")  # column unknown: both kept
    c = ratings.check(p)
    assert c["isr_last_date"] == "31-Jul-2025" and c["conflict"] is False  # U vs MU: same side, 1 apart


def test_unreadable_later_rated_row_means_no_verdict():
    text = ("RATINGS SUMMARY Outcome Unsatisfactory ISR RATINGS No. Date "
            "01 01-Jan-2020 Satisfactory Satisfactory 1.00 "
            "02 01-Jan-2021 Satisfactory 2.00 03 01-Jan-2022 Moderately Unsatisfactory SECTORS AND THEMES")
    assert ratings.check(ratings.parse(text)) is None  # rows 02/03 carry ratings the parser cannot place
