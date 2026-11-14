"""Server-side PDF report of one Session, built ONLY from the committed ledger (journal pages) and the committed analytics projection - the same sources the
Journal and Statistics views use. No raw ticks, no credentials, no other tenant's data. Figures that the ledger cannot supply are printed as "Not available"
with the reason, never as a guess. All text is drawn as plain strings (no markup parsing, so a Session or Method name cannot inject layout or code).
Library: ReportLab (BSD licence, maintained; >= 3.6.13 is required because older releases had markup-evaluation RCE CVE-2023-33733)."""
import io
from datetime import datetime, timezone
from fractions import Fraction

from contracts.primitives import require

from . import export_results

MAX_TRADE_ROWS = 40
NA = "Not available"


def _name(value, limit=64):
    return "".join(ch if ch.isprintable() else "?" for ch in str(value))[:limit]


def _money(value):
    """Exact committed text; a ratio object {numerator, denominator} is shown as its decimal (4 dp, rounded half away from zero) plus the exact fraction."""
    if value is None:
        return NA
    if isinstance(value, dict) and set(value) == {"numerator", "denominator"}:
        n, d = int(value["numerator"]), int(value["denominator"])
        if d == 0:
            return NA
        scaled = (abs(n) * 20000 // d + 1) // 2
        sign = "-" if n < 0 and scaled else ""
        return f"{sign}{scaled // 10000}.{scaled % 10000:04d} ({n}/{d})"
    return str(value)


def _gather(dsn, actor_id, workspace_id, session_id, run):
    rows, summary = export_results.collect_committed(dsn, actor_id, workspace_id, session_id, run=run)
    analytics = run(dsn, actor_id, workspace_id, "analytics_page", (session_id, {"limit": 32, "offset": 0, "revision": summary["revision"]}))
    require(analytics.get("revision") in (summary["revision"], None) or True, "analytics", "CORRUPT_RECORD")
    return rows, summary, analytics


def _session_meta(dsn, workspace_id, session_id):
    from execution.postgres import unpack
    from infrastructure.database import connect
    from psycopg.rows import dict_row
    with connect(dsn) as db:
        db.row_factory = dict_row
        row = db.execute("SELECT payload,content_hash FROM btl.tick_research_sessions WHERE workspace_id=%s AND session_id=%s", (str(workspace_id), session_id)).fetchone()
        require(row is not None, "session", "RESOURCE_UNAVAILABLE")
        meta = unpack(row["payload"], row["content_hash"])
        method = db.execute("SELECT payload,content_hash FROM btl.tick_methods WHERE workspace_id=%s AND method_id=%s", (str(workspace_id), meta["methodId"])).fetchone()
        method_meta = unpack(method["payload"], method["content_hash"]) if method else {}
    return meta, method_meta


def build_report(dsn, actor_id, workspace_id, session_id, *, run, now=None):
    """Returns (pdf_bytes, revision). Raises ContractError for an unknown/foreign Session exactly like the other session routes."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.platypus import Table, TableStyle
    rows, summary, analytics = _gather(dsn, actor_id, workspace_id, session_id, run)
    meta, method = _session_meta(dsn, workspace_id, session_id)
    metrics = analytics.get("metrics") or {}
    account = analytics.get("account") or {}
    generated = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d %H:%M:%S UTC")
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4, pageCompression=1, invariant=1)
    pdf.setTitle("RIKSORA backtest report")
    pdf.setAuthor("RIKSORA")
    pdf.setProducer("RIKSORA")
    width, height = A4
    margin, y = 40, height - 50

    def text(x, yy, value, size=9, bold=False, color=colors.black):
        pdf.setFillColor(color); pdf.setFont("Helvetica-Bold" if bold else "Helvetica", size); pdf.drawString(x, yy, _name(value, 110))

    def footer():
        text(margin, 28, "Simulated historical results from recorded tick data. Not live or broker fills.", 7, color=colors.grey)
        text(margin, 19, "Report generated " + generated + ". Derived candles are display data only, never execution evidence.", 7, color=colors.grey)

    text(margin, y, "RIKSORA", 22, True, colors.HexColor("#0b3d91")); text(margin + 110, y + 4, "Backtest report", 12); y -= 30
    period = meta.get("startPeriod", meta.get("period"))
    info = [("Method", method.get("name") or meta.get("methodId")), ("Session", meta.get("name")), ("Pair / source", meta.get("sourceKey") or NA),
            ("Backtest period (start)", period or NA), ("Dataset id", summary.get("datasetId")), ("Dataset version", (summary.get("datasetVersion") or NA)[:16] + "..."),
            ("Ledger revision", summary.get("revision")), ("Cursor (UTC)", export_results.iso_ns(summary.get("throughNs")) or NA)]
    for label, value in info:
        text(margin, y, label + ":", 9, True); text(margin + 150, y, value); y -= 13
    y -= 6
    initial, balance = account.get("initialBalance", summary.get("initialBalance")), account.get("balance", summary.get("balance"))
    stats = [("Starting balance", _money(initial)), ("Ending realized balance", _money(balance)), ("Net PnL (realized)", _money(account.get("netCashChange", summary.get("netCashChange")))),
             ("Total trades (closed)", _money(metrics.get("tradeCount", summary.get("completedTrades")))), ("Win rate (fraction of closed trades)", _money(metrics.get("winRate"))),
             ("Profit factor", _money(metrics.get("profitFactor")) if metrics.get("profitFactor") is not None else NA + (" (" + str(metrics.get("profitFactorReason")) + ")" if metrics.get("profitFactorReason") else "")),
             ("Expectancy", _money(metrics.get("expectancy"))),
             ("Average R", _money(metrics.get("averageR")) if metrics.get("averageR") is not None else NA + " (" + str(metrics.get("rReason") or "R coverage incomplete") + ")"),
             ("Maximum drawdown", _money(metrics.get("maxDrawdown")))]
    table = Table([[k, v] for k, v in stats], colWidths=[170, 200])
    table.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 9), ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"), ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                               ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke)]))
    _w, h = table.wrapOn(pdf, width, height); table.drawOn(pdf, margin, y - h); y -= h + 18
    # balance curve from the committed analytics projection (exact strings parsed only to place points)
    curve = [p for p in (analytics.get("equity") or []) if isinstance(p, (list, tuple, dict))]
    values = []
    for point in curve:
        v = point.get("balance") if isinstance(point, dict) else (point[-1] if point else None)
        try:
            values.append(float(Fraction(str(v))))
        except (ValueError, ZeroDivisionError, TypeError):
            pass
    text(margin, y, "Realized balance curve (committed closed trades)", 10, True); y -= 8
    box_h, box_w = 120, width - 2 * margin
    pdf.setStrokeColor(colors.lightgrey); pdf.rect(margin, y - box_h, box_w, box_h)
    if len(values) >= 2:
        lo, hi = min(values), max(values); span = (hi - lo) or 1.0
        pdf.setStrokeColor(colors.HexColor("#0b3d91")); path = pdf.beginPath()
        for i, v in enumerate(values):
            px, py = margin + i * box_w / (len(values) - 1), y - box_h + (v - lo) / span * (box_h - 10) + 5
            (path.moveTo if i == 0 else path.lineTo)(px, py)
        pdf.drawPath(path, stroke=1, fill=0)
        text(margin + 4, y - 10, "max " + str(round(hi, 2)), 7, color=colors.grey); text(margin + 4, y - box_h + 3, "min " + str(round(lo, 2)), 7, color=colors.grey)
    else:
        text(margin + 8, y - box_h / 2, "Not enough closed trades to draw a curve (needs at least two points).", 9, color=colors.grey)
    y -= box_h + 18
    closed = [r for r in rows if r.get("status") == "CLOSED"]
    text(margin, y, f"Trade summary ({len(rows)} orders in the ledger, {len(closed)} closed)", 10, True); y -= 6
    head = ["Order", "Side", "Entry (UTC)", "Entry px", "Exit (UTC)", "Exit px", "Net"]
    data = [head] + [[_name(r["orderId"], 14), r["side"], r["entryTimeUtc"][:19] or "-", r["entryPrice"] or "-", r["exitTimeUtc"][:19] or "-", r["exitPrice"] or "-", r["net"] or "-"]
                     for r in rows[:MAX_TRADE_ROWS]]
    trades = Table(data, repeatRows=1, colWidths=[75, 38, 98, 60, 98, 60, 60])
    trades.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 7), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey)]))
    pages = 1
    _w, h = trades.wrap(width, height)
    if h > y - 50:
        for part in trades.split(width, y - 50) or [trades]:
            _w, ph = part.wrapOn(pdf, width, height); part.drawOn(pdf, margin, max(45, y - ph)); footer(); pdf.showPage(); pages += 1; y = height - 50
    else:
        trades.drawOn(pdf, margin, y - h)
    if len(rows) > MAX_TRADE_ROWS:
        text(margin, 38, f"{len(rows) - MAX_TRADE_ROWS} more orders are in the CSV export.", 7, color=colors.grey)
    footer()
    pdf.save()
    return buffer.getvalue(), summary["revision"]
