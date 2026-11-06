"""Read-only PostgreSQL capacity snapshots for operator use.

Database/relation allocation is scoped to the current database; WAL counters
are server-global. Neither is per-Session storage or per-job WAL attribution.
"""
from datetime import datetime, timezone

from psycopg import Error as PsycopgError
from psycopg.rows import dict_row

from contracts.primitives import require
from .database import connect


ARTIFACT = "BTL-POSTGRES-CAPACITY-METRICS-1"


def _timestamp(value):
    return value.isoformat() if value is not None else None


def collect(dsn):
    """Read one repeatable, read-only snapshot without writing telemetry."""
    with connect(dsn) as db:
        db.row_factory = dict_row
        db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        identity = db.execute("""
            SELECT current_database() AS database_name,
                   current_setting('server_version_num')::integer AS server_version_num,
                   pg_postmaster_start_time() AS server_started_at,
                   clock_timestamp() AS measured_at,
                   pg_database_size(current_database()) AS database_bytes
        """).fetchone()
        relations = db.execute("""
            SELECT c.relname AS relation,
                   pg_table_size(c.oid) AS "tableToastBytes",
                   pg_indexes_size(c.oid) AS "indexBytes",
                   pg_total_relation_size(c.oid) AS "totalBytes"
            FROM pg_class c
            JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='btl' AND c.relkind IN ('r','p','m')
            ORDER BY c.relname
        """).fetchall()

        wal = None
        wal_status = "UNAVAILABLE"
        db.execute("SAVEPOINT postgres_metrics_wal")
        try:
            wal = db.execute("""
                SELECT stats_reset,wal_records,wal_fpi,wal_bytes,wal_buffers_full
                FROM pg_stat_wal
            """).fetchone()
            wal_status = "AVAILABLE_CUMULATIVE_COUNTER"
            db.execute("RELEASE SAVEPOINT postgres_metrics_wal")
        except PsycopgError:
            db.execute("ROLLBACK TO SAVEPOINT postgres_metrics_wal")
            db.execute("RELEASE SAVEPOINT postgres_metrics_wal")

    return {
        "schemaVersion": 1,
        "artifact": ARTIFACT,
        "measurementScope": "DATABASE_AND_SERVER_GLOBAL_SNAPSHOT",
        "databaseScope": "CURRENT_DATABASE",
        "walScope": "POSTGRESQL_SERVER",
        "database": identity["database_name"],
        "serverVersionNum": identity["server_version_num"],
        "serverStartedAt": _timestamp(identity["server_started_at"]),
        "measuredAt": _timestamp(identity["measured_at"]),
        "databaseBytes": identity["database_bytes"],
        "relations": [dict(row) for row in relations],
        "walStatus": wal_status,
        "walStatsResetAt": _timestamp(wal["stats_reset"]) if wal else None,
        "walRecordsSinceReset": int(wal["wal_records"]) if wal else None,
        "walFullPageImagesSinceReset": int(wal["wal_fpi"]) if wal else None,
        "walGeneratedBytesSinceReset": int(wal["wal_bytes"]) if wal else None,
        "walBuffersFullSinceReset": int(wal["wal_buffers_full"]) if wal else None,
        "retainedWalFileBytes": None,
        "perSessionWalBytes": None,
        "perSessionPhysicalBytes": None,
        "allocationNote": "databaseBytes covers the current database; relation sizes cover PostgreSQL table/TOAST/index allocation for each btl relation",
        "walNote": "wal_generated_bytes is a cumulative server counter since stats reset, not retained pg_wal disk allocation or per-job attribution",
    }


def compare(before, after):
    """Compare two valid snapshots; refuse cross-database or reset WAL deltas."""
    for snapshot in (before, after):
        require(type(snapshot) is dict and snapshot.get("artifact") == ARTIFACT,
                "metrics", "CORRUPT_RECORD")
        require(snapshot.get("schemaVersion") == 1 and type(snapshot.get("database")) is str and
                type(snapshot.get("serverVersionNum")) is int and
                type(snapshot.get("serverStartedAt")) is str and
                type(snapshot.get("databaseBytes")) is int and snapshot["databaseBytes"] >= 0 and
                type(snapshot.get("relations")) is list and type(snapshot.get("measuredAt")) is str and
                snapshot.get("walStatus") in ("AVAILABLE_CUMULATIVE_COUNTER", "UNAVAILABLE"),
                "metrics", "CORRUPT_RECORD")
        for row in snapshot["relations"]:
            require(type(row) is dict and type(row.get("relation")) is str and
                    all(type(row.get(field)) is int and row[field] >= 0
                        for field in ("tableToastBytes", "indexBytes", "totalBytes")),
                    "metrics", "CORRUPT_RECORD")
        require(len({row["relation"] for row in snapshot["relations"]}) == len(snapshot["relations"]),
                "metrics", "CORRUPT_RECORD")
        try:
            measured_at = datetime.fromisoformat(snapshot["measuredAt"])
            started_at = datetime.fromisoformat(snapshot["serverStartedAt"])
            reset_at = (datetime.fromisoformat(snapshot["walStatsResetAt"])
                        if snapshot.get("walStatsResetAt") is not None else None)
            require(measured_at.tzinfo is not None and started_at.tzinfo is not None and
                    (reset_at is None or reset_at.tzinfo is not None), "metrics", "CORRUPT_RECORD")
        except (TypeError, ValueError):
            require(False, "metrics", "CORRUPT_RECORD")
        if snapshot["walStatus"] == "AVAILABLE_CUMULATIVE_COUNTER":
            require(all(type(snapshot.get(field)) is int and snapshot[field] >= 0 for field in (
                "walRecordsSinceReset", "walFullPageImagesSinceReset", "walGeneratedBytesSinceReset",
                "walBuffersFullSinceReset")), "metrics", "CORRUPT_RECORD")
        else:
            require(all(snapshot.get(field) is None for field in (
                "walStatsResetAt", "walRecordsSinceReset", "walFullPageImagesSinceReset",
                "walGeneratedBytesSinceReset", "walBuffersFullSinceReset")),
                "metrics", "CORRUPT_RECORD")
    require(before["database"] == after["database"] and
            before["serverVersionNum"] == after["serverVersionNum"] and
            before["serverStartedAt"] == after["serverStartedAt"],
            "metrics", "REFUSED_METRIC_IDENTITY_MISMATCH")
    before_at = datetime.fromisoformat(before["measuredAt"]).astimezone(timezone.utc)
    after_at = datetime.fromisoformat(after["measuredAt"]).astimezone(timezone.utc)
    require(before_at <= after_at, "metrics", "REFUSED_METRIC_TIME_ORDER")

    before_relations = {row["relation"]: row for row in before["relations"]}
    after_relations = {row["relation"]: row for row in after["relations"]}
    relation_status = "COMPARABLE" if before_relations.keys() == after_relations.keys() else "SCHEMA_CHANGED"
    relation_deltas = None
    if relation_status == "COMPARABLE":
        relation_deltas = [
            {"relation": name,
             "tableToastBytesDelta": after_relations[name]["tableToastBytes"] - before_relations[name]["tableToastBytes"],
             "indexBytesDelta": after_relations[name]["indexBytes"] - before_relations[name]["indexBytes"],
             "totalBytesDelta": after_relations[name]["totalBytes"] - before_relations[name]["totalBytes"]}
            for name in sorted(before_relations)
        ]

    wal_comparable = (
        before["walStatus"] == after["walStatus"] == "AVAILABLE_CUMULATIVE_COUNTER" and
        before["walStatsResetAt"] is not None and
        before["walStatsResetAt"] == after["walStatsResetAt"] and
        type(before["walGeneratedBytesSinceReset"]) is int and
        type(after["walGeneratedBytesSinceReset"]) is int and
        after["walGeneratedBytesSinceReset"] >= before["walGeneratedBytesSinceReset"]
    )
    return {
        "schemaVersion": 1,
        "artifact": "BTL-POSTGRES-CAPACITY-DELTA-1",
        "database": before["database"],
        "fromMeasuredAt": before["measuredAt"],
        "toMeasuredAt": after["measuredAt"],
        "databaseBytesDelta": after["databaseBytes"] - before["databaseBytes"],
        "relationStatus": relation_status,
        "relationDeltas": relation_deltas,
        "walDeltaStatus": "COMPARABLE" if wal_comparable else "NOT_COMPARABLE_RESET_OR_UNAVAILABLE",
        "walGeneratedBytesDelta": (
            after["walGeneratedBytesSinceReset"] - before["walGeneratedBytesSinceReset"]
            if wal_comparable else None
        ),
        "retainedWalFileBytesDelta": None,
        "perSessionWalBytesDelta": None,
        "attribution": "CURRENT_DATABASE_AND_SERVER_WAL_GLOBAL_ONLY",
    }
