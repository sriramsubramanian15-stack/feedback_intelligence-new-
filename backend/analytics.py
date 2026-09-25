"""CSV cleanup, unique-user frequency, ranking and source evidence.

Pure Python: no AI or web dependencies, so these rules are easy to audit.
"""
import csv
import io
import re
from collections import defaultdict

PRIORITY_POINTS = {"low": 1, "medium": 2, "high": 3}
MAX_ROWS = 3000


def normalized(value):
    return re.sub(r"\s+", " ", value.strip()).casefold()


def read_feedback(raw):
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Save the CSV as CSV UTF-8 and upload it again.") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
    if not reader.fieldnames:
        raise ValueError("CSV is empty or has no header.")
    headers = [normalized(h) for h in reader.fieldnames]
    if len(set(headers)) != len(headers):
        raise ValueError("CSV column names must be unique.")
    required = {"user_id", "name", "feedback"}
    if not required.issubset(headers):
        raise ValueError("CSV needs user_id,name,feedback columns; date is optional.")
    rows, removed, seen = [], [], {}
    total = 0
    for index, values in enumerate(reader, 1):
        total += 1
        if total > MAX_ROWS:
            raise ValueError(f"Maximum {MAX_ROWS} rows per upload for this prototype.")
        if None in values:
            raise ValueError(f"Record {index}: extra columns. Put comments containing commas in double quotes.")
        row = {normalized(k): (v or "").strip() for k, v in values.items()}
        item = {"id": index, "user_id": row["user_id"], "name": row["name"],
                "feedback": row["feedback"], "date": row.get("date", "")}
        if not item["feedback"]:
            removed.append({**item, "reason": "Empty feedback", "status": "empty"})
            continue
        if not item["user_id"] or not item["name"]:
            raise ValueError(f"Record {index}: user_id and name are required for non-empty feedback.")
        if any(len(item[k]) > 200 for k in ("user_id", "name")) or len(item["feedback"]) > 6000:
            raise ValueError(f"Record {index}: user/name limit is 200 characters; feedback limit is 6000.")
        # Keep IDs case-sensitive: the source system defines identity, not a display name.
        key = (item["user_id"], normalized(item["feedback"]))
        if key in seen:
            removed.append({**item, "status": "duplicate", "reason": f"Same user and normalized comment as record {seen[key]}"})
            continue
        seen[key] = index
        rows.append(item)
    if not rows:
        raise ValueError("No non-empty feedback remains to analyze.")
    return rows, removed, total


def build_result(rows, analyses, rules, removed, total, company, context):
    """One user counts once in each topic, even across paraphrased repeats."""
    by_id = {item["id"]: item for item in analyses}
    expected = {row["id"] for row in rows}
    if set(by_id) != expected or len(analyses) != len(rows):
        raise ValueError("Analysis must contain every retained record exactly once.")
    rules_by_id = {r["id"]: r for r in rules}
    groups = defaultdict(list)
    audit = list(removed)
    retained_users = set()
    matched_rows = 0
    for row in rows:
        result = by_id[row["id"]]
        ids = result["rule_ids"]
        if len(ids) != len(set(ids)) or any(i not in rules_by_id for i in ids):
            raise ValueError("Analysis returned an invalid company topic ID.")
        if result["status"] != "matched" and ids:
            raise ValueError("Only matched feedback may contain topic IDs.")
        if result["status"] == "matched" and not ids:
            result = {
                **result,
                "status": "needs_review",
                "reason": "AI did not identify a company topic. Review manually.",
            }
        if result["status"] not in {"matched", "needs_review", "irrelevant", "no_action"}:
            raise ValueError("Unknown analysis status.")
        item = {**row, "status": result["status"], "reason": result["reason"],
                "topics": [rules_by_id[i]["label"] for i in ids]}
        audit.append(item)
        if result["status"] == "matched":
            matched_rows += 1
            retained_users.add(row["user_id"])
            for rule_id in ids:
                groups[rule_id].append(item)
    issues = []
    for rule_id, items in groups.items():
        rule = rules_by_id[rule_id]
        users = {r["user_id"] for r in items}
        points = PRIORITY_POINTS[rule["priority"]]
        # Fixed transparent weighting; no subjective AI severity or recency multiplier.
        frequency = len(users) / max(len(retained_users), 1)
        score = 60 * points / 3 + 40 * frequency
        issues.append({"id": rule_id, "issue": rule["label"], "phrases": rule["phrases"],
                       "priority": rule["priority"], "priority_points": points,
                       "unique_users": len(users), "frequency_percent": round(100 * frequency, 2),
                       "score": round(score, 2), "messages": len(items),
                       "repeat_mentions_not_counted": len(items) - len(users),
                       "evidence": items, "_sort_score": score})
    issues.sort(key=lambda i: (-i["_sort_score"], -i["priority_points"], -i["unique_users"], i["issue"].casefold()))
    for rank, issue in enumerate(issues, 1):
        issue["rank"] = rank
        del issue["_sort_score"]
    counts = {s: sum(r["status"] == s for r in audit)
              for s in ("duplicate", "empty", "irrelevant", "needs_review", "no_action")}
    return {"company": company, "context": context, "rules": rules,
            "formula": "60 × (priority points / 3) + 40 × (issue unique users / all matched unique users)",
            "summary": {"uploaded_rows": total, "matched_rows": matched_rows,
                        "matched_unique_users": len(retained_users), "issues": len(issues), **counts},
            "issues": issues, "audit": sorted(audit, key=lambda r: r["id"])}
