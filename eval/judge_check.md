# Hand check of the relevance judge (2026-10-24)

`python -m procintel.evaluate sample` (30 random judgments, seed 7) from 232 judged (question, passage) pairs.
Judge: `openai/saluki-27b` (Underdog-Saluki-27B-1.0 IQ2, thinking off). Labels below are mine, read from the passage.

**Agreement: 28 / 30 (93%).** Both disagreements are the judge marking a passage relevant that I would not
(lenient), so precision figures computed from these labels are likely a little optimistic.

| # | question | passage | judge | mine | note |
|---|---|---|---|---|---|
| 1 | q06 few or no responsive bids | 40108298:83 | not | not | |
| 2 | q03 procurement capacity lessons | 40130620:95 | not | not | |
| 3 | q07 payment delays to contractors | 40109568:83 | rel | rel | "delays stemmed from weak payment mechanisms" |
| 4 | q11 why contracts re-tendered | 40113490:79 | rel | **not** | lessons on procurement readiness; says nothing on re-tendering |
| 5 | q01 civil works delays | 40112810:101 | rel | rel | |
| 6 | q02 cancellations / terminations | 40130174:73 | rel | rel | terminations due to low contractor capacity |
| 7 | q14 community-based contracting | 40112622:23 | not | not | community behaviour change, not contracting |
| 8 | q09 consultant selection delays | 40112137:94 | rel | rel | slow recruitment of the O&M operator (borderline) |
| 9 | q02 cancellations / terminations | 40114650:163 | rel | rel | fragment, "hence the cancellation" (borderline) |
| 10 | q06 few or no responsive bids | 40107742:102 | not | not | |
| 11 | q10 role of STEP | 40128714:86 | not | not | M&E, not STEP |
| 12 | q02 cancellations / terminations | 40130174:58 | rel | rel | |
| 13 | q09 consultant selection delays | 40108298:70 | not | not | consultants' capacity, not selection |
| 14 | q04 COVID-19 effects | 40130174:43 | rel | rel | |
| 15 | q01 civil works delays | 40124776:53 | rel | rel | |
| 16 | q02 cancellations / terminations | 40113905:89 | not | not | says termination was prevented |
| 17 | q08 weak specifications / ToR | 40130697:98 | rel | **not** | TA execution constraints, not specifications |
| 18 | q07 payment delays to contractors | 40110921:74 | not | not | insolvency and safeguards |
| 19 | q02 cancellations / terminations | 40125342:91 | rel | rel | |
| 20 | q05 land acquisition | 40124776:82 | not | not | grievances; no large-scale land acquisition |
| 21 | q02 cancellations / terminations | 40112137:119 | not | not | slow procurement plan |
| 22 | q10 role of STEP | 40115389:96 | rel | rel | |
| 23 | q07 payment delays to contractors | 40111934:88 | not | not | currency shocks (borderline) |
| 24 | q02 cancellations / terminations | 40114321:107 | rel | rel | partial loan cancellation |
| 25 | q10 role of STEP | 40116240:87 | rel | rel | |
| 26 | q03 procurement capacity lessons | 40113549:67 | rel | rel | |
| 27 | q04 COVID-19 effects | 40130697:105 | rel | rel | |
| 28 | q11 why contracts re-tendered | 40109765:77 | rel | rel | "several re-biddings because of procurement capacity gaps" |
| 29 | q11 why contracts re-tendered | 40111933:86 | rel | rel | mentions re-tendering terminated contracts (weak) |
| 30 | q15 restructuring and procurement plans | 40114321:49 | rel | rel | subprojects cancelled at restructuring |
