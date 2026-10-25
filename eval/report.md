# Evaluation report (2026-10-25 05:58 UTC)

Models: answers and relevance judge `openai/saluki-27b`; embeddings `openai/embeddinggemma-2`; decision `http://127.0.0.1:8082`.
15 answerable questions; 232 judged (question, passage) pairs; 1 passages in today's results are not judged yet (run `evaluate judge`).
Recall is against the pooled relevant set (BM25 top 10 + hybrid top 10), so it is an upper bound.
Relevance judge vs a hand check of 30 judgments: 28/30 agree, both misses lenient (eval/judge_check.md).
Faithfulness is judged by the answer model and by an independent model, `openai/qwen3-vl-8b`.

## Retrieval

| metric | now | previous run |
|---|---|---|
| BM25 precision@5 | 0.64 | 0.64 |
| Hybrid precision@5 | 0.77 | 0.77 |
| BM25 recall@10 | 0.62 | 0.62 |
| Hybrid recall@10 | 0.76 | 0.76 |
| Evidence gate precision | 0.92 | 0.77 |

## Answers

Measured in this run.

| metric | value |
|---|---|
| Answerable questions answered (not refused) | 15/15 |
| Answer sentences supported by their citations (answer model as judge) | 53/56 |
| Answer sentences supported by their citations (independent judge) | 54/56 |
| Unanswerable questions refused | 5/5 |
| Median time per question | 32.7 s |

## User feedback

31 responses logged.

| page | useful | not useful | citations flagged |
|---|---|---|---|
| ask | 0 | 0 | 0 |
| assess | 0 | 0 | 0 |

## Per question

| id | question | relevant in pool | BM25 P@5 | hybrid P@5 | gate kept / precision | answer |
|---|---|---|---|---|---|---|
| q01 | What caused delays in civil works contracts? | 13 | 1.00 | 1.00 | 5 / 1.00 | 3/4 supported |
| q02 | Why were procurement processes cancelled or contracts terminated? | 14 | 1.00 | 1.00 | 5 / 1.00 | 4/4 supported |
| q03 | What lessons were learned about procurement capacity of implementing agencies? | 13 | 0.80 | 1.00 | 5 / 1.00 | 4/4 supported |
| q04 | How did the COVID-19 pandemic affect procurement and contract implementation? | 13 | 1.00 | 1.00 | 5 / 1.00 | 4/4 supported |
| q05 | What problems did land acquisition and resettlement cause for project implementation? | 11 | 0.40 | 0.80 | 5 / 1.00 | 4/4 supported |
| q06 | Why did tenders receive few or no responsive bids? | 2 | 0.20 | 0.40 | 3 / 0.67 | 2/3 supported |
| q07 | How did delays in payments to contractors affect works? | 12 | 0.80 | 0.80 | 5 / 1.00 | 4/4 supported |
| q08 | What problems were caused by weak technical specifications or terms of reference? | 6 | 0.60 | 1.00 | 5 / 1.00 | 4/4 supported |
| q09 | How was the selection of consultants delayed? | 5 | 0.40 | 0.60 | 5 / 0.80 (unjudged: 1) | 3/3 supported |
| q10 | What role did STEP play in procurement monitoring? | 11 | 0.60 | 1.00 | 5 / 1.00 | 3/3 supported |
| q11 | Why were contracts re-tendered? | 7 | 0.40 | 0.40 | 3 / 1.00 | 3/3 supported |
| q12 | How did contractor performance problems affect road projects? | 11 | 0.60 | 0.80 | 5 / 0.80 | 4/4 supported |
| q13 | What fiduciary or financial management weaknesses affected procurement? | 9 | 0.60 | 0.60 | 5 / 0.60 | 4/4 supported |
| q14 | How did community-based or labor-based contracting work in practice? | 9 | 0.80 | 0.40 | 5 / 1.00 | 4/4 supported |
| q15 | What were the effects of restructuring on procurement plans? | 10 | 0.40 | 0.80 | 5 / 1.00 | 3/4 supported |
| q16 | What is the boiling point of tungsten? | – | – | – | – | refused |
| q17 | Who won the 2018 FIFA World Cup? | – | – | – | – | refused |
| q18 | How did blockchain-based e-procurement platforms reduce bid rigging in these projects? | – | – | – | – | refused |
| q19 | What procurement lessons came from building the stadiums for the Paris 2024 Olympic Games? | – | – | – | – | refused |
| q20 | What was the average bid price for satellite launch services? | – | – | – | – | refused |
