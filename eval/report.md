# Evaluation report (2026-10-25 14:37 UTC)

Models: answers and relevance judge `openai/saluki-27b`; embeddings `openai/embeddinggemma-2`; decision `http://127.0.0.1:8082`.
80 answerable questions; 1248 judged (question, passage) pairs.
Recall is against the pooled relevant set (BM25 top 10 + hybrid top 10), so it is an upper bound.
Relevance judge vs hand checks of 60 judgments: 54/60 agree (28/30 and 26/30), 5 of the 6 misses lenient (eval/judge_check.md).
Faithfulness is judged by the answer model and by an independent model, `openai/qwen3-vl-8b`.

## Retrieval

| metric | now | previous run |
|---|---|---|
| BM25 precision@5 | 0.54 | 0.54 |
| Hybrid precision@5 | 0.70 | 0.70 |
| BM25 recall@10 | 0.55 | 0.55 |
| Hybrid recall@10 | 0.78 | 0.78 |
| Evidence gate precision | 0.90 (not re-run; from 2026-10-25 10:17 UTC) | – |

## Answers

Not re-run this time; figures from 2026-10-25 10:17 UTC.

| metric | value |
|---|---|
| Answerable questions answered (not refused) | 77/80 |
| Answer sentences supported by their citations (answer model as judge) | 277/285 |
| Answer sentences supported by their citations (independent judge) | 282/285 |
| Unanswerable questions refused | 20/20 |
| Median time per question | 34.0 s |

## User feedback

38 responses logged.

| page | useful | not useful | citations flagged |
|---|---|---|---|
| ask | 0 | 0 | 0 |
| assess | 0 | 0 | 0 |

## Per question

| id | question | relevant in pool | BM25 P@5 | hybrid P@5 | gate kept / precision | answer |
|---|---|---|---|---|---|---|
| q01 | What caused delays in civil works contracts? | 13 | 1.00 | 1.00 | 0 / – | – |
| q02 | Why were procurement processes cancelled or contracts terminated? | 14 | 1.00 | 1.00 | 0 / – | – |
| q03 | What lessons were learned about procurement capacity of implementing agencies? | 13 | 0.80 | 1.00 | 0 / – | – |
| q04 | How did the COVID-19 pandemic affect procurement and contract implementation? | 13 | 1.00 | 1.00 | 0 / – | – |
| q05 | What problems did land acquisition and resettlement cause for project implementation? | 11 | 0.40 | 0.80 | 0 / – | – |
| q06 | Why did tenders receive few or no responsive bids? | 2 | 0.20 | 0.40 | 0 / – | – |
| q07 | How did delays in payments to contractors affect works? | 12 | 0.80 | 0.80 | 0 / – | – |
| q08 | What problems were caused by weak technical specifications or terms of reference? | 6 | 0.60 | 1.00 | 0 / – | – |
| q09 | How was the selection of consultants delayed? | 5 | 0.40 | 0.60 | 0 / – | – |
| q10 | What role did STEP play in procurement monitoring? | 11 | 0.60 | 1.00 | 0 / – | – |
| q11 | Why were contracts re-tendered? | 7 | 0.40 | 0.40 | 0 / – | – |
| q12 | How did contractor performance problems affect road projects? | 11 | 0.60 | 0.80 | 0 / – | – |
| q13 | What fiduciary or financial management weaknesses affected procurement? | 9 | 0.60 | 0.60 | 0 / – | – |
| q14 | How did community-based or labor-based contracting work in practice? | 9 | 0.80 | 0.40 | 0 / – | – |
| q15 | What were the effects of restructuring on procurement plans? | 10 | 0.40 | 0.80 | 0 / – | – |
| q21 | How did price escalation or inflation affect contract costs? | 13 | 0.80 | 0.80 | 0 / – | – |
| q22 | What problems did exchange rate movements cause for procurement or project costs? | 10 | 0.40 | 1.00 | 0 / – | – |
| q23 | How did insecurity or conflict affect procurement and works? | 10 | 1.00 | 0.80 | 0 / – | – |
| q24 | How was the contingent emergency response component (CERC) used? | 9 | 0.80 | 0.80 | 0 / – | – |
| q25 | What role did UN agencies play in procurement or implementation? | 13 | 0.60 | 1.00 | 0 / – | – |
| q26 | What were the benefits or problems of hands-on expanded implementation support (HEIS)? | 8 | 0.60 | 0.60 | 0 / – | – |
| q27 | What problems were found with procurement plans? | 12 | 0.40 | 1.00 | 0 / – | – |
| q28 | What caused delays in bid evaluation? | 10 | 0.60 | 0.80 | 0 / – | – |
| q29 | How did a limited number of bidders or a thin local market affect procurement? | 9 | 0.60 | 0.80 | 0 / – | – |
| q30 | What experience was reported with e-procurement systems? | 2 | 0.00 | 0.20 | 0 / – | – |
| q31 | How were direct contracting or single-source selection used? | 2 | 0.20 | 0.20 | 0 / – | – |
| q32 | What misprocurement cases were reported? | 1 | 0.00 | 0.00 | 0 / – | – |
| q33 | How did public-private partnership arrangements work out? | 4 | 0.20 | 0.60 | 0 / – | – |
| q34 | What problems arose in procuring medical equipment? | 4 | 0.20 | 0.40 | 0 / – | – |
| q35 | How was vaccine procurement or delivery organised? | 12 | 0.80 | 1.00 | 0 / – | – |
| q36 | What difficulties occurred in procuring IT systems or software? | 7 | 0.60 | 0.40 | 0 / – | – |
| q37 | What problems affected school construction or classroom works? | 7 | 0.40 | 1.00 | 0 / – | – |
| q38 | What issues arose with solar energy procurement or installation? | 5 | 0.00 | 0.60 | 0 / – | – |
| q39 | What problems affected water supply works contracts? | 10 | 0.40 | 0.80 | 0 / – | – |
| q40 | What fraud or corruption issues were found? | 4 | 0.20 | 0.20 | 0 / – | – |
| q41 | How did grievance redress mechanisms work for project-affected people? | 12 | 0.60 | 0.80 | 0 / – | – |
| q42 | How did results-based financing or disbursement-linked indicators affect implementation? | 11 | 0.80 | 0.60 | 0 / – | – |
| q43 | How did staff turnover in implementing agencies affect the project? | 19 | 1.00 | 1.00 | 0 / – | – |
| q44 | What weaknesses did project implementation units have? | 11 | 1.00 | 1.00 | 0 / – | – |
| q45 | What problems did delays in counterpart funding cause? | 10 | 0.80 | 1.00 | 0 / – | – |
| q46 | How did customs clearance affect deliveries of goods? | 6 | 1.00 | 1.00 | 0 / – | – |
| q47 | How was retroactive financing used? | 7 | 0.80 | 1.00 | 0 / – | – |
| q48 | What did audits find about project financial management? | 15 | 1.00 | 1.00 | 0 / – | – |
| q49 | How well did contractors comply with environmental and social management plans? | 13 | 0.80 | 0.80 | 0 / – | – |
| q50 | What occupational health and safety problems occurred at work sites? | 8 | 0.60 | 1.00 | 0 / – | – |
| q51 | What caused cost overruns? | 13 | 0.60 | 1.00 | 0 / – | – |
| q52 | What changes came out of mid-term reviews? | 13 | 0.80 | 0.80 | 0 / – | – |
| q53 | Why were closing dates extended? | 11 | 0.60 | 0.60 | 0 / – | – |
| q54 | Why were project funds cancelled? | 10 | 1.00 | 1.00 | 0 / – | – |
| q55 | What problems were caused by poorly prepared terms of reference for consultants? | 2 | 0.00 | 0.40 | 0 / – | – |
| q56 | What contract disputes arose and how were they resolved? | 7 | 0.20 | 0.40 | 0 / – | – |
| q57 | How was STEP used to track procurement? | 12 | 1.00 | 1.00 | 0 / – | – |
| q58 | What role did prior review by the World Bank play in procurement? | 8 | 0.40 | 0.60 | 0 / – | – |
| q59 | How did supervision consultants perform? | 10 | 0.60 | 0.60 | 0 / – | – |
| q60 | How did performance-based or output-based contracts work? | 5 | 0.60 | 0.60 | 0 / – | – |
| q61 | What lessons were learned about road maintenance contracts? | 10 | 0.60 | 0.80 | 0 / – | – |
| q62 | How did the COVID-19 pandemic delay goods deliveries? | 10 | 0.40 | 1.00 | 0 / – | – |
| q63 | What problems did weak engineering designs cause during construction? | 2 | 0.40 | 0.00 | 0 / – | – |
| q64 | Why were some contracts terminated for poor contractor performance? | 7 | 0.60 | 0.80 | 0 / – | – |
| q65 | How did late payments affect contractors' willingness to work? | 5 | 0.20 | 0.40 | 0 / – | – |
| q66 | What lessons were learned about project readiness at approval? | 10 | 0.60 | 1.00 | 0 / – | – |
| q67 | How did natural disasters such as floods or cyclones affect works? | 14 | 1.00 | 0.80 | 0 / – | – |
| q68 | How did the choice of procurement method affect timelines? | 11 | 0.60 | 0.80 | 0 / – | – |
| q69 | What problems were caused by the decentralised implementation of procurement? | 2 | 0.20 | 0.00 | 0 / – | – |
| q70 | How did procurement capacity building or training for agencies work? | 14 | 0.80 | 0.80 | 0 / – | – |
| q71 | What problems did land compensation payments cause? | 10 | 0.80 | 1.00 | 0 / – | – |
| q72 | How did gender considerations affect project activities? | 13 | 0.80 | 1.00 | 0 / – | – |
| q73 | What were the reasons for project restructuring? | 9 | 0.40 | 0.80 | 0 / – | – |
| q74 | How were monitoring and evaluation weaknesses reported? | 14 | 1.00 | 1.00 | 0 / – | – |
| q75 | What lessons were learned about technical assistance contracts? | 13 | 0.60 | 1.00 | 0 / – | – |
| q76 | Why did firms stop showing up to bid? | 1 | 0.00 | 0.20 | 0 / – | – |
| q77 | Why did building work take so much longer than planned? | 5 | 0.00 | 0.40 | 0 / – | – |
| q78 | Why was the money not spent on time? | 5 | 0.00 | 0.40 | 0 / – | – |
| q79 | What went wrong with hiring advisers? | 4 | 0.40 | 0.20 | 0 / – | – |
| q80 | Why did some suppliers deliver late? | 2 | 0.00 | 0.40 | 0 / – | – |
| q81 | What happened when contractors ran out of cash? | 6 | 0.00 | 0.80 | 0 / – | – |
| q82 | Why did the government take so long to approve things? | 3 | 0.20 | 0.20 | 0 / – | – |
| q83 | What made bigger contracts harder to award? | 8 | 0.40 | 0.60 | 0 / – | – |
| q84 | Why did prices end up higher than expected? | 5 | 0.20 | 0.40 | 0 / – | – |
| q85 | What did the teams learn about planning purchases early? | 4 | 0.00 | 0.40 | 0 / – | – |
