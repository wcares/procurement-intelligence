"""Past contracts most similar to a planned package's description, with how they went.

Candidates are awarded packages of the same procurement group whose description was embedded (table package_vec,
`python -m procintel.core.embed`). Two rankings are merged by reciprocal rank fusion: vector similarity (EmbeddingGemma,
multilingual) and shared rare words, which keeps exact terms and acronyms that vectors blur ("EEWS" found "Management
for EEWS Development" only with the word ranking). Hand-checked top 5 on 4 descriptions (2026-10-25): roads 5/5,
medical equipment 5/5, a supervision consultant for early warning systems about 3/5. Among the closest 3k, contracts
with a known tender-to-award time are shown first (only ~1 in 5 awarded packages has one).
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from procintel.answering.answer import terms
from procintel.core import db, embed, paths, vector_index
from procintel.ingestion import fx

DB_PATH = paths.DB_PATH
POOL = 50


class Similar:
    def __init__(self, db_path: Path = DB_PATH):
        con = db.connect(db_path, read_only=True)
        self.rows: list[dict] = []
        self.vectors = None
        if embed.available() and con.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'package_vec'").fetchone():
            q = con.execute("""
                SELECT k.package_id, k.project_id, p.name AS project_name, p.country_code, k.proc_group, k.method_code,
                       k.description, k.tender_to_award_days, k.price_currency, k.price_amount,
                       year(k.award_date::DATE) AS award_year, k.rebid_evidence, {vec}
                FROM package_vec v JOIN package k USING (package_id) LEFT JOIN project p USING (project_id)
                WHERE v.model = ? AND v.dim = ?""".format(vec="v.vec" if vector_index.backend() == "memory" else "NULL AS vec"),
                [embed.model_name(), embed.dim()])
            cols = [d[0] for d in q.description]
            data = q.fetchall()
            table = fx.rates(con)
            self.rows = [dict(zip(cols[:-1], r[:-1])) for r in data]
            for r in self.rows:
                r["value_usd"] = fx.to_usd(r["price_amount"], r["price_currency"], r["award_year"], table)
                r["terms"] = terms(r["description"] or "")
            keys = [r["package_id"] for r in self.rows]
            self.vectors = (vector_index.open_index("packages", keys,
                                                    lambda: np.asarray([r[-1] for r in data], dtype=np.float32))
                            if data else None)
        con.close()
        df: dict[str, int] = {}
        for r in self.rows:
            for t in r["terms"]:
                df[t] = df.get(t, 0) + 1
        n = max(len(self.rows), 1)
        self.idf = {t: math.log(n / c) for t, c in df.items()}

    def available(self) -> bool:
        return self.vectors is not None and len(self.rows) > 0

    def search(self, description: str, proc_group: str, k: int = 5) -> list[dict]:
        if not self.available() or not description.strip():
            return []
        same = np.array([r["proc_group"] == proc_group for r in self.rows])
        if not same.any():
            return []
        q = embed.embed([embed.format_query(description)])[0]
        vec_rank = vector_index.ranking(self.vectors, q, same, POOL)
        qt = terms(description)
        ws = [(sum(self.idf.get(t, 0) for t in qt & r["terms"]), i) for i, r in enumerate(self.rows) if same[i]]
        word_rank = [i for s, i in sorted(ws, reverse=True)[:POOL] if s > 0]
        fused: dict[int, float] = {}
        for ranking in (vec_rank, word_rank):
            for rank, i in enumerate(ranking):
                fused[i] = fused.get(i, 0.0) + 1.0 / (60 + rank + 1)
        # among the closest 3k, show contracts with a known tender-to-award time first (that is what planners compare);
        # relevance order is kept within each group
        close = sorted(fused, key=fused.get, reverse=True)[:3 * k]
        close.sort(key=lambda i: self.rows[i]["tender_to_award_days"] is None)
        out = []
        for i in close[:k]:
            r = self.rows[i]
            out.append({"packageId": r["package_id"], "projectId": r["project_id"], "projectName": r["project_name"] or "",
                        "countryCode": r["country_code"] or "", "method": r["method_code"] or "",
                        "description": r["description"], "tenderToAwardDays": r["tender_to_award_days"],
                        "valueUsd": round(r["value_usd"]) if r["value_usd"] and r["value_usd"] > 0 else None,  # 0 = not given
                        "rebid": r["rebid_evidence"] is not None})
        return out
