# Evaluation report (2026-10-25 10:17 UTC)

Models: answers and relevance judge `openai/saluki-27b`; embeddings `openai/embeddinggemma-2`; decision `http://127.0.0.1:8082`.
80 answerable questions; 1248 judged (question, passage) pairs; 11 passages in today's results are not judged yet (run `evaluate judge`).
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
| Evidence gate precision | 0.90 | 0.90 |

## Answers

Measured in this run.

| metric | value |
|---|---|
| Answerable questions answered (not refused) | 77/80 |
| Answer sentences supported by their citations (answer model as judge) | 277/285 |
| Answer sentences supported by their citations (independent judge) | 282/285 |
| Unanswerable questions refused | 20/20 |
| Median time per question | 34.0 s |

## User feedback

33 responses logged.

| page | useful | not useful | citations flagged |
|---|---|---|---|
| ask | 0 | 0 | 0 |
| assess | 0 | 0 | 0 |

## Per question

| id | question | relevant in pool | BM25 P@5 | hybrid P@5 | gate kept / precision | answer |
|---|---|---|---|---|---|---|
| q01 | What caused delays in civil works contracts? | 13 | 1.00 | 1.00 | 5 / 1.00 | 4/4 supported |
| q02 | Why were procurement processes cancelled or contracts terminated? | 14 | 1.00 | 1.00 | 5 / 1.00 | 3/4 supported |
| q03 | What lessons were learned about procurement capacity of implementing agencies? | 13 | 0.80 | 1.00 | 5 / 1.00 | 4/4 supported |
| q04 | How did the COVID-19 pandemic affect procurement and contract implementation? | 13 | 1.00 | 1.00 | 5 / 1.00 | 4/4 supported |
| q05 | What problems did land acquisition and resettlement cause for project implementation? | 11 | 0.40 | 0.80 | 5 / 1.00 | 4/4 supported |
| q06 | Why did tenders receive few or no responsive bids? | 2 | 0.20 | 0.40 | 3 / 0.67 | 2/2 supported |
| q07 | How did delays in payments to contractors affect works? | 12 | 0.80 | 0.80 | 5 / 1.00 | 4/4 supported |
| q08 | What problems were caused by weak technical specifications or terms of reference? | 6 | 0.60 | 1.00 | 5 / 1.00 | 4/4 supported |
| q09 | How was the selection of consultants delayed? | 5 | 0.40 | 0.60 | 5 / 0.80 (unjudged: 1) | 4/4 supported |
| q10 | What role did STEP play in procurement monitoring? | 11 | 0.60 | 1.00 | 5 / 1.00 | 3/3 supported |
| q11 | Why were contracts re-tendered? | 7 | 0.40 | 0.40 | 3 / 1.00 | 3/3 supported |
| q12 | How did contractor performance problems affect road projects? | 11 | 0.60 | 0.80 | 5 / 0.80 | 4/4 supported |
| q13 | What fiduciary or financial management weaknesses affected procurement? | 9 | 0.60 | 0.60 | 5 / 0.60 | 4/4 supported |
| q14 | How did community-based or labor-based contracting work in practice? | 9 | 0.80 | 0.40 | 5 / 1.00 | 4/4 supported |
| q15 | What were the effects of restructuring on procurement plans? | 10 | 0.40 | 0.80 | 5 / 1.00 | 4/4 supported |
| q21 | How did price escalation or inflation affect contract costs? | 13 | 0.80 | 0.80 | 5 / 0.80 | 4/4 supported |
| q22 | What problems did exchange rate movements cause for procurement or project costs? | 10 | 0.40 | 1.00 | 5 / 1.00 | 4/4 supported |
| q23 | How did insecurity or conflict affect procurement and works? | 10 | 1.00 | 0.80 | 5 / 1.00 | 3/3 supported |
| q24 | How was the contingent emergency response component (CERC) used? | 9 | 0.80 | 0.80 | 5 / 0.80 (unjudged: 1) | 4/4 supported |
| q25 | What role did UN agencies play in procurement or implementation? | 13 | 0.60 | 1.00 | 5 / 1.00 | 4/4 supported |
| q26 | What were the benefits or problems of hands-on expanded implementation support (HEIS)? | 8 | 0.60 | 0.60 | 4 / 1.00 | 4/4 supported |
| q27 | What problems were found with procurement plans? | 12 | 0.40 | 1.00 | 5 / 1.00 | 4/4 supported |
| q28 | What caused delays in bid evaluation? | 10 | 0.60 | 0.80 | 5 / 1.00 | 3/4 supported |
| q29 | How did a limited number of bidders or a thin local market affect procurement? | 9 | 0.60 | 0.80 | 5 / 1.00 | 3/4 supported |
| q30 | What experience was reported with e-procurement systems? | 2 | 0.00 | 0.20 | 5 / 0.40 | 3/3 supported |
| q31 | How were direct contracting or single-source selection used? | 2 | 0.20 | 0.20 | 2 / 1.00 | 4/4 supported |
| q32 | What misprocurement cases were reported? | 1 | 0.00 | 0.00 | 1 / 1.00 | refused |
| q33 | How did public-private partnership arrangements work out? | 4 | 0.20 | 0.60 | 4 / 0.75 | refused |
| q34 | What problems arose in procuring medical equipment? | 4 | 0.20 | 0.40 | 3 / 1.00 | 4/4 supported |
| q35 | How was vaccine procurement or delivery organised? | 12 | 0.80 | 1.00 | 5 / 1.00 | 4/4 supported |
| q36 | What difficulties occurred in procuring IT systems or software? | 7 | 0.60 | 0.40 | 3 / 1.00 | 3/3 supported |
| q37 | What problems affected school construction or classroom works? | 7 | 0.40 | 1.00 | 3 / 0.67 (unjudged: 1) | 4/4 supported |
| q38 | What issues arose with solar energy procurement or installation? | 5 | 0.00 | 0.60 | 5 / 0.80 (unjudged: 1) | 4/4 supported |
| q39 | What problems affected water supply works contracts? | 10 | 0.40 | 0.80 | 5 / 0.80 | 4/4 supported |
| q40 | What fraud or corruption issues were found? | 4 | 0.20 | 0.20 | 3 / 0.67 | 4/4 supported |
| q41 | How did grievance redress mechanisms work for project-affected people? | 12 | 0.60 | 0.80 | 5 / 0.80 | 2/3 supported |
| q42 | How did results-based financing or disbursement-linked indicators affect implementation? | 11 | 0.80 | 0.60 | 5 / 0.60 | 3/3 supported |
| q43 | How did staff turnover in implementing agencies affect the project? | 19 | 1.00 | 1.00 | 5 / 1.00 | 3/3 supported |
| q44 | What weaknesses did project implementation units have? | 11 | 1.00 | 1.00 | 5 / 1.00 | 3/3 supported |
| q45 | What problems did delays in counterpart funding cause? | 10 | 0.80 | 1.00 | 5 / 1.00 | 4/4 supported |
| q46 | How did customs clearance affect deliveries of goods? | 6 | 1.00 | 1.00 | 4 / 1.00 | 3/3 supported |
| q47 | How was retroactive financing used? | 7 | 0.80 | 1.00 | 5 / 1.00 | 4/4 supported |
| q48 | What did audits find about project financial management? | 15 | 1.00 | 1.00 | 5 / 1.00 | 4/4 supported |
| q49 | How well did contractors comply with environmental and social management plans? | 13 | 0.80 | 0.80 | 5 / 1.00 | 4/4 supported |
| q50 | What occupational health and safety problems occurred at work sites? | 8 | 0.60 | 1.00 | 5 / 1.00 | 4/4 supported |
| q51 | What caused cost overruns? | 13 | 0.60 | 1.00 | 5 / 1.00 | 4/4 supported |
| q52 | What changes came out of mid-term reviews? | 13 | 0.80 | 0.80 | 5 / 1.00 | 4/4 supported |
| q53 | Why were closing dates extended? | 11 | 0.60 | 0.60 | 5 / 0.80 | 3/3 supported |
| q54 | Why were project funds cancelled? | 10 | 1.00 | 1.00 | 5 / 1.00 | 4/4 supported |
| q55 | What problems were caused by poorly prepared terms of reference for consultants? | 2 | 0.00 | 0.40 | 2 / 1.00 | 3/4 supported |
| q56 | What contract disputes arose and how were they resolved? | 7 | 0.20 | 0.40 | 4 / 0.75 (unjudged: 1) | 3/3 supported |
| q57 | How was STEP used to track procurement? | 12 | 1.00 | 1.00 | 5 / 1.00 | 4/4 supported |
| q58 | What role did prior review by the World Bank play in procurement? | 8 | 0.40 | 0.60 | 3 / 1.00 | 3/3 supported |
| q59 | How did supervision consultants perform? | 10 | 0.60 | 0.60 | 5 / 0.80 | 4/4 supported |
| q60 | How did performance-based or output-based contracts work? | 5 | 0.60 | 0.60 | 3 / 1.00 | 4/4 supported |
| q61 | What lessons were learned about road maintenance contracts? | 10 | 0.60 | 0.80 | 5 / 1.00 | 4/4 supported |
| q62 | How did the COVID-19 pandemic delay goods deliveries? | 10 | 0.40 | 1.00 | 5 / 1.00 | 3/3 supported |
| q63 | What problems did weak engineering designs cause during construction? | 2 | 0.40 | 0.00 | 1 / 1.00 | 2/3 supported |
| q64 | Why were some contracts terminated for poor contractor performance? | 7 | 0.60 | 0.80 | 2 / 1.00 | 2/3 supported |
| q65 | How did late payments affect contractors' willingness to work? | 5 | 0.20 | 0.40 | 4 / 1.00 | 4/4 supported |
| q66 | What lessons were learned about project readiness at approval? | 10 | 0.60 | 1.00 | 5 / 1.00 | 4/4 supported |
| q67 | How did natural disasters such as floods or cyclones affect works? | 14 | 1.00 | 0.80 | 5 / 1.00 | 4/4 supported |
| q68 | How did the choice of procurement method affect timelines? | 11 | 0.60 | 0.80 | 5 / 0.80 | 3/3 supported |
| q69 | What problems were caused by the decentralised implementation of procurement? | 2 | 0.20 | 0.00 | 3 / 0.33 (unjudged: 1) | 4/4 supported |
| q70 | How did procurement capacity building or training for agencies work? | 14 | 0.80 | 0.80 | 5 / 1.00 | 4/4 supported |
| q71 | What problems did land compensation payments cause? | 10 | 0.80 | 1.00 | 5 / 1.00 | 4/4 supported |
| q72 | How did gender considerations affect project activities? | 13 | 0.80 | 1.00 | 5 / 1.00 | 4/4 supported |
| q73 | What were the reasons for project restructuring? | 9 | 0.40 | 0.80 | 5 / 1.00 | 3/4 supported |
| q74 | How were monitoring and evaluation weaknesses reported? | 14 | 1.00 | 1.00 | 5 / 1.00 | 4/4 supported |
| q75 | What lessons were learned about technical assistance contracts? | 13 | 0.60 | 1.00 | 5 / 1.00 | 4/4 supported |
| q76 | Why did firms stop showing up to bid? | 1 | 0.00 | 0.20 | 3 / 0.33 (unjudged: 1) | refused |
| q77 | Why did building work take so much longer than planned? | 5 | 0.00 | 0.40 | 5 / 1.00 | 4/4 supported |
| q78 | Why was the money not spent on time? | 5 | 0.00 | 0.40 | 5 / 1.00 | 4/4 supported |
| q79 | What went wrong with hiring advisers? | 4 | 0.40 | 0.20 | 3 / 1.00 | 3/3 supported |
| q80 | Why did some suppliers deliver late? | 2 | 0.00 | 0.40 | 2 / 0.50 (unjudged: 1) | 3/3 supported |
| q81 | What happened when contractors ran out of cash? | 6 | 0.00 | 0.80 | 5 / 1.00 | 4/4 supported |
| q82 | Why did the government take so long to approve things? | 3 | 0.20 | 0.20 | 3 / 0.67 (unjudged: 1) | 4/4 supported |
| q83 | What made bigger contracts harder to award? | 8 | 0.40 | 0.60 | 2 / 1.00 | 3/3 supported |
| q84 | Why did prices end up higher than expected? | 5 | 0.20 | 0.40 | 4 / 0.50 (unjudged: 1) | 4/4 supported |
| q85 | What did the teams learn about planning purchases early? | 4 | 0.00 | 0.40 | 5 / 0.80 (unjudged: 1) | 3/3 supported |
| q16 | What is the boiling point of tungsten? | – | – | – | – | refused |
| q17 | Who won the 2018 FIFA World Cup? | – | – | – | – | refused |
| q18 | How did blockchain-based e-procurement platforms reduce bid rigging in these projects? | – | – | – | – | refused |
| q19 | What procurement lessons came from building the stadiums for the Paris 2024 Olympic Games? | – | – | – | – | refused |
| q20 | What was the average bid price for satellite launch services? | – | – | – | – | refused |
| q86 | What procurement problems affected the high-speed rail lines? | – | – | – | – | refused |
| q87 | How were stadium construction contracts procured? | – | – | – | – | refused |
| q88 | What lessons came from procuring parts for the space station? | – | – | – | – | refused |
| q89 | Why were fighter jet contracts delayed? | – | – | – | – | refused |
| q90 | How was the casino concession tendered? | – | – | – | – | refused |
| q91 | What delayed the Antarctic research station contracts? | – | – | – | – | refused |
| q92 | How did metaverse platforms change bid submission? | – | – | – | – | refused |
| q93 | What was the average price of satellite launch contracts per kilogram? | – | – | – | – | refused |
| q94 | Which bidder won the Mars rover contract? | – | – | – | – | refused |
| q95 | How did quantum computers speed up bid evaluation? | – | – | – | – | refused |
| q96 | Who painted the Mona Lisa? | – | – | – | – | refused |
| q97 | What is the capital of Australia? | – | – | – | – | refused |
| q98 | How do I bake sourdough bread? | – | – | – | – | refused |
| q99 | What is the speed of light in a vacuum? | – | – | – | – | refused |
| q100 | Who wrote the novel War and Peace? | – | – | – | – | refused |
