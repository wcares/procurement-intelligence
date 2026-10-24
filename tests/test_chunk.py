from procintel.chunk import chunk_document, strip_page_furniture

# Shape copied from a real ICR page (P163035): numbered paragraph, footnote block, footer, running header.
PAGE = (
    "B. KEY FACTORS DURING IMPLEMENTATION\n"
    "24.     The labor-based approach generated tangible outputs at low unit costs, while simultaneously\n"
    "transferring a significant share of civil works expenditure directly to community members as wages.\n"
    "\n\n"
    "7\n"
    "  One of the SMEs in the project opted to discontinue participation in the program and failed to submit\n"
    "established deadline\n"
    "8\n"
    "  �?� NCA Category 8 refers to the entry-level contractor classification\n"
    "\n"
    "                                                Official Use Only                    Page 8\n"
)
NEXT_PAGE = (
    "            The World Bank\n"
    "            Improved Livelihood Opportunities (P163035)\n"
    "25.     Procurement delays affected the second tranche because bidders lacked the required registration\n"
    "category and two tenders had to be re-advertised.\n"
)


def test_footnotes_and_footer_are_removed():
    lines = strip_page_furniture(PAGE)
    text = " ".join(lines)
    assert "One of the SMEs" not in text
    assert "Official Use Only" not in text
    assert "labor-based approach" in text


def test_numbered_paragraphs_become_anchored_chunks():
    chunks = chunk_document(PAGE + "\x0c" + NEXT_PAGE)
    by_para = {c.para: c for c in chunks}
    assert set(by_para) == {"24", "25"}
    assert by_para["24"].section == "B. Key Factors During Implementation"
    assert "re-advertised" in by_para["25"].text
    assert "The World Bank" not in by_para["25"].text  # running header dropped
    assert all("�" not in c.text and "SMEs" not in c.text for c in chunks)


def test_table_block_is_marked():
    table = (
        "C. EFFICIENCY\n"
        "Component           Appraisal     Actual      Percent\n"
        "Roads               12.40         10.10       81\n"
        "Training            2.00          1.85        92\n"
        "Management          3.10          3.30        106\n"
        "\n"
    )
    chunks = chunk_document(table)
    assert chunks and chunks[0].kind == "table"


def test_long_paragraph_is_split_on_sentences():
    long = "V. LESSONS AND RECOMMENDATIONS\n31.     " + " ".join(f"Sentence number {i} explains a procurement delay in detail." for i in range(60)) + "\n"
    chunks = chunk_document(long)
    assert len(chunks) > 1
    assert all(len(c.text) <= 1400 for c in chunks)
    assert all(c.para == "31" for c in chunks)


def test_official_use_only_at_top_of_page_does_not_drop_the_page():
    page = (
        "                 Official Use Only\n"
        "A. CONTEXT AT APPRAISAL\n"
        "12. The project financed rural roads and the procurement plan was approved late, which delayed the first bids.\n"
        "13. A second paragraph about contractor capacity and how it affected the timeline of the works contracts.\n"
    )
    chunks = chunk_document(page)
    assert [c.para for c in chunks] == ["12", "13"]
    assert all("Official Use Only" not in c.text for c in chunks)


def test_numbered_list_inside_paragraph_is_not_a_new_paragraph():
    text = (
        "V. LESSONS AND RECOMMENDATIONS\n"
        "40. The evaluation identified three procurement lessons that apply to similar operations:\n"
        "1. Prepare bidding documents before effectiveness so the first tenders are not delayed.\n"
        "2. Use framework agreements for recurrent small purchases of goods.\n"
        "41. A separate paragraph about monitoring and evaluation arrangements and data quality.\n"
    )
    chunks = chunk_document(text)
    assert [c.para for c in chunks] == ["40", "41"]
    assert "framework agreements" in chunks[0].text


def test_list_right_after_a_heading_is_not_a_paragraph():
    text = (
        "IV. KEY FACTORS\n"
        "20. Procurement was centralized in the ministry and approvals took several months for each contract.\n"
        "V. LESSONS AND RECOMMENDATIONS\n"
        "1. Decentralize approvals for small contracts so they do not queue behind large works packages.\n"
        "21. The next numbered paragraph discusses the lesson in more detail with the supporting evidence.\n"
    )
    chunks = chunk_document(text)
    assert [c.para for c in chunks if c.para] == ["20", "21"]
