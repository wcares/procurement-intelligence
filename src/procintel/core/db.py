"""Every database connection goes through here, so the storage engine is a setting, not code.

PROCINTEL_DB_URL selects it:
  (unset)                      DuckDB files in the data folder (procintel.core.paths): the local default
  postgresql://user:pw@host/db Postgres, through DuckDB's postgres extension: the same SQL runs, tables live in
                               Postgres, and several processes (api, workers) can write at once. The main database
                               maps to schema "public", the feedback log to "feedback", the job queue to "jobs".

Paths other than the three known databases (tests, scratch copies) always open as DuckDB files.
"""
from __future__ import annotations

import os
from pathlib import Path

import duckdb

from procintel.core import paths

SCHEMAS = {paths.DB_PATH: "public", paths.FEEDBACK_DB: "feedback", paths.JOBS_DB: "jobs"}


def url() -> str:
    return os.environ.get("PROCINTEL_DB_URL", "").strip()


def backend() -> str:
    return "postgres" if url().startswith(("postgres://", "postgresql://")) else "duckdb"


def connect(path: Path | str | None = None, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    p = Path(path) if path is not None else paths.DB_PATH
    schema = SCHEMAS.get(p)
    if schema is None or backend() == "duckdb":
        return duckdb.connect(str(p), read_only=read_only)
    return _postgres(schema, read_only)


def _postgres(schema: str, read_only: bool) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    try:
        con.execute("LOAD postgres")
    except duckdb.Error as e:  # not installed: installing downloads it, which is a deliberate step
        con.close()
        raise RuntimeError("the DuckDB postgres extension is not installed: run `python -m procintel.core.db install`") from e
    dsn = url().replace("'", "''")
    con.execute(f"ATTACH '{dsn}' AS pg (TYPE postgres{', READ_ONLY' if read_only else ''})")
    if not read_only:
        con.execute(f'CREATE SCHEMA IF NOT EXISTS pg."{schema}"')
    con.execute(f'USE pg."{schema}"')
    return con


def copy_to_postgres() -> dict[str, int]:
    """Copy every table of the local DuckDB files into Postgres (replacing tables of the same name)."""
    if backend() != "postgres":
        raise RuntimeError("set PROCINTEL_DB_URL to a postgresql:// URL first")
    counts: dict[str, int] = {}
    for path, schema in SCHEMAS.items():
        if not path.exists():
            continue
        con = _postgres(schema, read_only=False)
        con.execute(f"ATTACH '{path}' AS src (READ_ONLY)")
        for (t,) in con.execute("SELECT table_name FROM duckdb_tables() WHERE database_name = 'src' ORDER BY 1").fetchall():
            con.execute(f'DROP TABLE IF EXISTS pg."{schema}"."{t}"')
            cols = con.execute("SELECT column_name, data_type FROM duckdb_columns() WHERE database_name = 'src' "
                               "AND table_name = ? ORDER BY column_index", [t]).fetchall()
            # Postgres has no unnamed composite types: struct columns travel as JSON text; JSON columns become text too,
            # because the extension cannot update a Postgres json column (it sends text, which Postgres refuses)
            sel = ", ".join(f'to_json("{c}")::VARCHAR AS "{c}"' if "STRUCT" in ty
                            else f'"{c}"::VARCHAR AS "{c}"' if ty == "JSON" else f'"{c}"' for c, ty in cols)
            con.execute(f'CREATE TABLE pg."{schema}"."{t}" AS SELECT {sel} FROM src."{t}"')
            counts[f"{schema}.{t}"] = con.execute(f'SELECT count(*) FROM pg."{schema}"."{t}"').fetchone()[0]
        con.close()
    return counts


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["install"]:
        duckdb.connect().execute("INSTALL postgres")
        print("installed the DuckDB postgres extension")
    elif sys.argv[1:] == ["copy-to-postgres"]:
        for k, n in copy_to_postgres().items():
            print(f"{k}: {n}")
    else:
        print(f"backend: {backend()}")
