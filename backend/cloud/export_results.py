"""Server-side CSV export of a Session's trade history from the COMMITTED ledger (journal pages), never from client state or chart candles.

One row per order/trade. Every price and money value is the exact decimal text the canonical engine committed (no float anywhere). Nanosecond times are
emitted as exact integers and as UTC ISO-8601 with nine fractional digits built from integer arithmetic. Provenance columns (session, dataset id/version,
ledger revision) are repeated on every row so a single file stays self-describing when it is opened in a spreadsheet.
Security: identity and tenant checks are those of the research `run` (membership of the workspace is verified on every call, a foreign or unknown Session
answers like an unknown one); text cells that start with a spreadsheet formula character are neutralised; the export is bounded.
"""
import csv
import io
import re
from datetime import datetime, timezone

from contracts.primitives import ContractError, require

MAX_EXPORT_ORDERS = 50_000
PAGE = 32                                                   # execution.journal.MAX_JOURNAL_PAGE_SIZE
COLUMNS = ("sessionId", "datasetId", "datasetVersion", "ledgerRevision", "orderId", "workflow", "orderType", "side", "status", "quantity",
           "entryTimeNs", "entryTimeUtc", "entryPrice", "exitTimeNs", "exitTimeUtc", "exitPrice", "exitReason", "gross", "commission", "net",
           "netCashChange", "plannedInitialRisk", "riskPercent", "rMultiple", "rMultipleExact", "rReason", "mae", "mfe", "sl", "tp", "remaining", "durationNs")
_NS = re.compile(r"[0-9]{1,19}")


def iso_ns(value):
    """Exact UTC ISO-8601 with nine fractional digits from an integer nanosecond count (text or int); empty for None."""
    if value is None or value == "":
        return ""
    require(_NS.fullmatch(str(value)) is not None, "time", "INVALID_INPUT")
    total = int(value)
    seconds, nanos = divmod(total, 10**9)
    return datetime.fromtimestamp(seconds, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + f".{nanos:09d}Z"


def ratio_parts(value):
    """(decimal text to 8 places half away from zero, exact 'n/d') for a committed ratio {numerator, denominator}; (None, None) for anything else."""
    if isinstance(value, dict) and set(value) == {"numerator", "denominator"}:
        n, d = int(value["numerator"]), int(value["denominator"])
        if d <= 0:
            return None, None
        scaled = (abs(n) * 2 * 10**8 // d + 1) // 2
        sign = "-" if n < 0 and scaled else ""
        return f"{sign}{scaled // 10**8}.{scaled % 10**8:08d}", f"{n}/{d}"
    return None, None


def _cell(value):
    if value is None:
        return ""
    text = str(value)
    if re.fullmatch(r"-?[0-9]+/[0-9]+", text):
        return text                                              # an exact fraction is inert text (no function, no reference)
    # CSV/formula injection: a cell that a spreadsheet would execute is prefixed with an apostrophe (numbers such as -1.5 stay numbers)
    if text and text[0] in "=+-@\t\r" and not re.fullmatch(r"-?[0-9]+(\.[0-9]+)?", text):
        return "'" + text
    return text


def order_row(order, provenance):
    exit_ns = order.get("exitTimeNs")
    r_decimal, r_exact = ratio_parts(order.get("rMultiple"))
    return {
        **provenance, "orderId": order.get("id"), "workflow": order.get("workflow"), "orderType": order.get("orderType"), "side": order.get("side"),
        "status": order.get("status"), "quantity": order.get("quantity"),
        "entryTimeNs": order.get("entryTimeNs"), "entryTimeUtc": iso_ns(order.get("entryTimeNs")), "entryPrice": order.get("entryPrice"),
        "exitTimeNs": exit_ns, "exitTimeUtc": iso_ns(exit_ns), "exitPrice": order.get("exitPrice"), "exitReason": order.get("exitReason"),
        "gross": order.get("gross"), "commission": order.get("commission"), "net": order.get("net"), "netCashChange": order.get("netCashChange"),
        "plannedInitialRisk": order.get("plannedInitialRisk"), "riskPercent": order.get("riskPercent"), "rMultiple": r_decimal if r_decimal is not None else order.get("rMultiple"), "rMultipleExact": r_exact,
        "rReason": order.get("rReason"), "mae": order.get("mae"), "mfe": order.get("mfe"), "sl": order.get("sl"), "tp": order.get("tp"),
        "remaining": order.get("remaining"), "durationNs": order.get("durationNs"),
    }


def rows_to_csv(rows):
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(COLUMNS)
    for row in rows:
        writer.writerow([_cell(row.get(column)) for column in COLUMNS])
    return out.getvalue()


def collect_committed(dsn, actor_id, workspace_id, session_id, *, run):
    """Walk the journal pages of one Session at one committed revision: (rows, summary). Shared by the CSV and PDF exports so both read the same ledger."""
    for attempt in range(3):                                    # a revision that advances while paging restarts the walk (bounded)
        summary = run(dsn, actor_id, workspace_id, "summary", (session_id,))
        provenance = dict(sessionId=session_id, datasetId=summary.get("datasetId"), datasetVersion=summary.get("datasetVersion"),
                          ledgerRevision=summary.get("revision"))
        rows, cursor = [], None
        try:
            while True:
                page = run(dsn, actor_id, workspace_id, "journal_page", (session_id, {"limit": PAGE, "cursor": cursor}))
                require(page.get("artifact") == "BTL-TICK-JOURNAL-PAGE-1" and page.get("financialAuthority") == "COMMITTED_EVENTS_ONLY",
                        "journal", "CORRUPT_RECORD")
                if page["revision"] != provenance["ledgerRevision"]:
                    raise ContractError("STALE_REVISION", "export")
                rows.extend(order_row(order, provenance) for order in page["orders"])
                require(len(rows) <= MAX_EXPORT_ORDERS, "export", "REFUSED_EXPORT_LIMIT")
                if page["complete"]:
                    return rows, summary
                cursor = page["nextCursor"]
        except ContractError as error:
            if error.code not in ("STALE_REVISION", "INVALID_CURSOR") or attempt == 2:
                raise
    raise ContractError("STALE_REVISION", "export")


def export_session_csv(dsn, actor_id, workspace_id, session_id, *, run):
    """Return (csv_text, revision, order_count) for the committed ledger of one Session."""
    rows, summary = collect_committed(dsn, actor_id, workspace_id, session_id, run=run)
    return rows_to_csv(rows), summary.get("revision"), len(rows)
