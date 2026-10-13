"""Step 10: analyst review actions (procedure Section 7, review screen).

  approve   accept an item. For a metric row with low-confidence figures a comment is required
            (what was checked against the source); those figures become 'manually_verified', and
            the check is recorded so it survives re-runs while the value is unchanged.
  reject    reject an item (for example a guidance candidate that is not guidance).
  comment   add a note; does not count as reviewing the item.
  correct   metric rows only: a new value with a mandatory reason. The original extraction is
            kept; the correction is a new figure that supersedes it, and comparisons are redone.

Every action is written to reviews and to the audit log.
"""
import json
from decimal import Decimal, InvalidOperation

from copilot import compare, db, report, verify

ACTIONS = {"approve", "reject", "comment", "correct"}


class ReviewError(Exception):
    pass


def record(conn, cfg, company, quarter, item, reviewer, action, comment=None, new_value=None):
    if not reviewer or not reviewer.strip():
        raise ReviewError("a reviewer name is required")
    if action not in ACTIONS:
        raise ReviewError(f"unknown action {action!r}")
    rep = report.build(conn, cfg, company, quarter)
    if item not in rep["items"]:
        raise ReviewError(f"{item} is not an item of this report")
    row = next((r for r in rep["content"]["rows"] if r["key"] == item), None)
    old = new = None
    comment = (comment or "").strip() or None

    if action == "comment" and not comment:
        raise ReviewError("a comment needs text")
    if action == "approve" and row:
        low = report.low_confidence(row, company)
        if low and not comment:
            raise ReviewError("this row has low-confidence figures: say what you checked against the source")
        for label, f, key in low:
            conn.execute("INSERT INTO reviews (report, item, reviewer, action, comment, old_value, time)"
                         " VALUES (?, ?, ?, 'approve', ?, ?, ?)",
                         (rep["id"], key, reviewer, comment, f["value"], db.now()))
            conn.execute("UPDATE figures SET status = 'manually_verified', note = ? WHERE company = ? AND metric = ?"
                         " AND segment IS ? AND period = ? AND value = ? AND status = 'low_confidence'",
                         (f"manually checked by {reviewer}: {comment}", company, f["metric"], f["segment"],
                          f["period"], f["value"]))
            db.audit(conn, "figure_manually_verified", key, {"reviewer": reviewer, "comment": comment}, user=reviewer)
        if low:
            conn.commit()
            for period in {f["period"] for _, f, _ in low}:
                verify.run(conn, cfg, company, period, user=reviewer)   # derived figures follow their inputs
    if action == "correct":
        if row is None:
            raise ReviewError("only metric rows can be corrected")
        if not comment:
            raise ReviewError("a correction needs a reason")
        try:
            new = Decimal(str(new_value).replace(",", "").strip())
        except (InvalidOperation, TypeError):
            raise ReviewError(f"not a number: {new_value!r}")
        cur = compare.pick(conn, company, row["metric"], row["segment"], quarter, quarter)
        if cur is None or cur["value"] is None:
            raise ReviewError("there is no reported value to correct")
        original = cur["supersedes"] or cur["id"]
        old = cur["value"]
        conn.execute(
            "INSERT INTO figures (company, quarter, metric, period, basis, segment, value, unit, original_value,"
            " original_unit, document_id, source_ref, source_detail, method, derivation, status, note, supersedes,"
            " reason, created_at) SELECT company, quarter, metric, period, basis, segment, ?, unit, original_value,"
            " original_unit, document_id, source_ref, source_detail, 'manual', derivation, 'manually_verified', ?, ?, ?, ?"
            " FROM figures WHERE id = ?",
            (db.to_db(new), f"corrected by {reviewer}", original, comment, db.now(), original))
        db.audit(conn, "figure_corrected", item, {"old": old, "new": str(new), "reason": comment,
                                                  "original_figure": original}, user=reviewer)
        compare.run(conn, cfg, company, "all")
    conn.execute("INSERT INTO reviews (report, item, reviewer, action, comment, old_value, new_value, time)"
                 " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                 (rep["id"], item, reviewer, action, comment, old, None if new is None else str(new), db.now()))
    db.audit(conn, f"review_{action}", f"{rep['id']}/{item}", {"comment": comment}, user=reviewer)
    conn.commit()
