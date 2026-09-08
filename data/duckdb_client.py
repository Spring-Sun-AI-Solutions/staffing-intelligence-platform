"""
data/duckdb_client.py
DuckDB client for fast analytics queries.

DuckDB runs as an embedded file-based database — no server needed.
It connects directly to Postgres via the postgres_scanner extension,
so it reads live data without any ETL pipeline.

Usage:
    from data.duckdb_client import query_duckdb, get_duckdb_conn

    df = query_duckdb("SELECT * FROM candidates LIMIT 10")
    conn = get_duckdb_conn()
"""
import logging
import os
from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd

from data.logger import get_logger

logger = get_logger("data.duckdb")

DUCKDB_PATH = os.getenv("DUCKDB_PATH", "./data/analytics.duckdb")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://sip:sippassword@localhost:5432/staffing")

_conn: Optional[duckdb.DuckDBPyConnection] = None


def get_duckdb_conn() -> duckdb.DuckDBPyConnection:
    """
    Get or create a DuckDB connection with Postgres attached.
    Connection is reused across calls (singleton per process).
    """
    global _conn

    if _conn is not None:
        try:
            _conn.execute("SELECT 1")
            return _conn
        except Exception:
            _conn = None

    logger.info(f"Connecting to DuckDB at {DUCKDB_PATH}")
    _conn = duckdb.connect(DUCKDB_PATH)

    # Install and load postgres_scanner extension
    try:
        _conn.execute("INSTALL postgres_scanner")
        _conn.execute("LOAD postgres_scanner")

        # Attach Postgres database so we can query it directly
        _conn.execute(f"""
            ATTACH '{DATABASE_URL}' AS pg (TYPE POSTGRES, READ_ONLY)
        """)
        logger.info("DuckDB connected with Postgres attached")

    except Exception as e:
        logger.warning(f"Could not attach Postgres to DuckDB: {e}")
        logger.info("DuckDB running in standalone mode — using cached data only")
        _setup_standalone_tables(_conn)

    return _conn


def _setup_standalone_tables(conn: duckdb.DuckDBPyConnection):
    """
    Create local DuckDB tables from Postgres data.
    Used when postgres_scanner extension is not available.
    """
    try:
        import psycopg2
        pg_conn = psycopg2.connect(DATABASE_URL)

        tables = ["candidates", "clients", "placements", "timesheets", "payroll", "jobs"]
        for table in tables:
            try:
                df = pd.read_sql(f"SELECT * FROM {table}", pg_conn)
                conn.register(f"pg_{table}", df)
                conn.execute(f"CREATE OR REPLACE VIEW {table} AS SELECT * FROM pg_{table}")
                logger.info(f"DuckDB: loaded {len(df)} rows from {table}")
            except Exception as e:
                logger.warning(f"Could not load {table}: {e}")

        pg_conn.close()
    except Exception as e:
        logger.error(f"Standalone DuckDB setup failed: {e}")


def query_duckdb(sql: str, params: Optional[list] = None) -> pd.DataFrame:
    """
    Execute a SQL query against DuckDB and return a DataFrame.

    Automatically prefixes table names with 'pg.' when Postgres is attached.

    Args:
        sql:    SQL query string
        params: optional list of parameters for parameterised queries

    Returns:
        pandas DataFrame with query results
    """
    conn = get_duckdb_conn()
    try:
        if params:
            result = conn.execute(sql, params).df()
        else:
            result = conn.execute(sql).df()
        logger.debug(f"DuckDB query returned {len(result)} rows")
        return result
    except Exception as e:
        logger.error(f"DuckDB query failed: {e}\nSQL: {sql}")
        raise


def refresh_cache():
    """
    Reload all Postgres data into DuckDB standalone tables.
    Called by the nightly scheduler to keep cache fresh.
    """
    global _conn
    if _conn is not None:
        try:
            _conn.close()
        except Exception:
            pass
        _conn = None
    get_duckdb_conn()
    logger.info("DuckDB cache refreshed")


# ── Pre-built analytics queries ───────────────────────────────────────────────

def get_placement_funnel(
    client_id: Optional[int] = None,
    recruiter_id: Optional[int] = None,
    days: int = 90,
) -> pd.DataFrame:
    """
    Placement funnel counts: req→submission→interview→offer→hire.
    Uses DuckDB for fast aggregation.
    """
    where_clauses = [f"submitted_at >= CURRENT_DATE - INTERVAL '{days} days'"]
    if client_id:
        where_clauses.append(f"client_id = {client_id}")
    if recruiter_id:
        where_clauses.append(f"recruiter_id = {recruiter_id}")

    where = " AND ".join(where_clauses)

    sql = f"""
    SELECT
        stage,
        COUNT(*) AS count,
        ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) AS pct
    FROM placements
    WHERE {where}
    GROUP BY stage
    ORDER BY CASE stage
        WHEN 'submitted'  THEN 1
        WHEN 'interview'  THEN 2
        WHEN 'offer'      THEN 3
        WHEN 'hire'       THEN 4
        WHEN 'rejected'   THEN 5
        ELSE 6
    END
    """
    try:
        return query_duckdb(sql)
    except Exception as e:
        logger.warning(f"Funnel query failed: {e}")
        from db.queries import get_placement_funnel_counts
        return get_placement_funnel_counts(client_id)


def get_recruiter_kpis(days: int = 30) -> pd.DataFrame:
    """
    Recruiter performance KPIs: submissions, interviews, placements, conversion rate.
    """
    sql = f"""
    SELECT
        r.id            AS recruiter_id,
        r.name          AS recruiter_name,
        COUNT(p.id)     AS total_submissions,
        SUM(CASE WHEN p.stage IN ('interview','offer','hire') THEN 1 ELSE 0 END) AS interviews,
        SUM(CASE WHEN p.stage = 'hire' THEN 1 ELSE 0 END) AS placements,
        ROUND(
            SUM(CASE WHEN p.stage = 'hire' THEN 1 ELSE 0 END) * 100.0
            / NULLIF(COUNT(p.id), 0), 1
        ) AS conversion_rate_pct,
        AVG(p.match_score) AS avg_match_score
    FROM recruiters r
    LEFT JOIN placements p ON p.recruiter_id = r.id
        AND p.submitted_at >= CURRENT_DATE - INTERVAL '{days} days'
    GROUP BY r.id, r.name
    ORDER BY placements DESC, conversion_rate_pct DESC
    """
    try:
        return query_duckdb(sql)
    except Exception as e:
        logger.warning(f"Recruiter KPI query failed, using Postgres: {e}")
        from db.queries import get_recruiters, get_placements
        recruiters = get_recruiters()
        placements = get_placements()
        rows = []
        for _, r in recruiters.iterrows():
            p = placements[placements["recruiter_id"] == r["id"]]
            subs = len(p)
            ints = len(p[p["stage"].isin(["interview", "offer", "hire"])])
            hires = len(p[p["stage"] == "hire"])
            rows.append({
                "recruiter_id": r["id"],
                "recruiter_name": r["name"],
                "total_submissions": subs,
                "interviews": ints,
                "placements": hires,
                "conversion_rate_pct": round(hires / subs * 100, 1) if subs else 0.0,
                "avg_match_score": round(p["match_score"].mean(), 1) if subs else 0.0,
            })
        return pd.DataFrame(rows)


def get_revenue_by_client(months: int = 6) -> pd.DataFrame:
    """Revenue breakdown by client for the last N months."""
    sql = f"""
    SELECT
        c.name          AS client_name,
        DATE_TRUNC('month', p.period) AS month,
        SUM(p.bill_rate)  AS revenue,
        AVG(p.margin_pct) AS avg_margin_pct,
        COUNT(DISTINCT p.contractor_id) AS headcount
    FROM payroll p
    JOIN placements pl ON pl.candidate_id = p.contractor_id
    JOIN clients c     ON c.id = pl.client_id
    WHERE p.period >= CURRENT_DATE - INTERVAL '{months} months'
    GROUP BY c.name, DATE_TRUNC('month', p.period)
    ORDER BY month DESC, revenue DESC
    """
    try:
        return query_duckdb(sql)
    except Exception as e:
        logger.warning(f"Revenue by client query failed: {e}")
        return pd.DataFrame(columns=["client_name", "month", "revenue",
                                     "avg_margin_pct", "headcount"])
