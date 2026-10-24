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


# Header/footer shapes copied from real ICRs (40114321, 40111934, 40130914, 40130423, 40111896)
def test_wrapped_running_header_is_removed_up_to_the_project_id():
    page = (
        "          The World Bank\n"
        "          East-West Roads project (Almaty-Korgos Section): Western Europe - Western China\n"
        "          ICR DOCUMENT\n"
        "          International Transit Corridor (CAREC - 1b) (P128050)\n"
        "\n"
        "30.     Two works contracts were re-tendered after the first bids exceeded the cost estimate by a wide margin.\n"
    )
    text = " ".join(strip_page_furniture(page))
    assert "Western China" not in text and "CAREC" not in text
    assert "re-tendered" in text


def test_mixed_case_icr_document_header_and_bare_page_footer_are_removed():
    page = (
        "B. FIDUCIARY COMPLIANCE\n"
        "81. Capacity-building mitigation measures were progressively implemented, including dissemination of appropriate\n"
        "                                                                                                       Page 19\n"
    )
    nxt = (
        "          The World Bank\n"
        "          Energy and Mineral Sectors Strengthening Project II (P170850)                                             ICR Document\n"
        "\n"
        "procurement approaches, and capacity-building activities among implementing agencies.\n"
    )
    chunks = chunk_document(page + "\x0c" + nxt)
    assert [c.para for c in chunks] == ["81"]
    assert "Page 19" not in chunks[0].text and "P170850" not in chunks[0].text
    assert "appropriate procurement approaches" in chunks[0].text


def test_page_number_glued_to_body_text_is_stripped_but_references_are_kept():
    lines = strip_page_furniture(
        "Page 3 enhanced resilience to climate shocks, as the appraisal document noted (Page 6).\n"
        "Strictly Confidential                                                        Page 15\n"
        "Page 1 of 46\n"
    )
    assert [l.strip() for l in lines] == ["enhanced resilience to climate shocks, as the appraisal document noted (Page 6)."]


def test_project_id_in_body_text_near_page_top_is_not_treated_as_header():
    page = (
        "A. CONTEXT AT APPRAISAL\n"
        "12. The project built on the earlier Rural Roads Project (P112233), whose contractors had the required registration.\n"
        "13. Procurement of the works followed the same approach and took four months on average for each package.\n"
    )
    assert [c.para for c in chunk_document(page)] == ["12", "13"]


def test_footer_between_pages_does_not_split_an_unnumbered_block():
    text = ("C. OUTCOME\nThe roads programme reached all eleven districts and the maintenance contracts were\n"
            "                    Official Use Only                    Page 8\n\x0c"
            "awarded through community contracting, which kept unit costs well below the appraisal estimate.\n")
    chunks = chunk_document(text)
    assert len(chunks) == 1 and "contracts were awarded through community contracting" in chunks[0].text


def test_running_header_without_a_page_break_is_removed():
    # extraction of 40128492 has no form feed before this header block
    text = ("A. CONTEXT AT APPRAISAL\n"
            "5. The city faced recurrent flooding and the drainage works were procured in three large lots.\n"
            "The World Bank\n"
            "Benin - Stormwater Management and Urban Resilience Project (P167359) ICR DOCUMENT\n"
            "Official Use Only\n"
            "6. Bids for the second lot exceeded the estimate and the lot was re-tendered after a design review.\n")
    chunks = chunk_document(text)
    assert [c.para for c in chunks] == ["5", "6"]
    assert all("P167359" not in c.text and "Stormwater" not in c.text for c in chunks)


def test_project_id_in_paragraph_after_header_does_not_extend_the_header():
    # 40113730: header, blank line, then a numbered paragraph that also mentions the project id
    page = ("          The World Bank\n"
            "          COVID-19 Strategic Preparedness and Response Program (SPRP) (P173789)        ICR DOCUMENT\n\n\n"
            "8. On April 2, 2020, the Board approved the program, utilizing\n"
            "   the MPA (P173789), and on the same day approved the first 25 projects.\n")
    text = " ".join(l.strip() for l in strip_page_furniture(page) if l.strip())
    assert text.startswith("8. On April 2, 2020") and "the MPA (P173789)" in text


def test_text_without_sentence_breaks_is_still_capped():
    # shape of a real table row run (Table 9.1 in a Bangladesh ICR): numbers, no sentence end, 5,000 characters
    row = "Akhaura 1.00 0.85 0.65 0.50 0.75 0.75 1.00 1.00 0.00 0.50 0.50 1.00 0.40 0.25 0.00 "
    text = "C. EFFICIENCY\n31. " + row * 60 + "\n"
    chunks = chunk_document(text)
    assert len(chunks) > 1 and all(len(c.text) <= 1400 for c in chunks)
    assert " ".join(c.text for c in chunks).split() == (row * 60).split()  # nothing lost, nothing cut mid-word
