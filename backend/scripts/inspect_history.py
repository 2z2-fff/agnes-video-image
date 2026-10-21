"""Diagnostics: dump recent history records with ages."""

import time

from app import history


def main():
    now = int(time.time())
    recs = history.list_records(limit=50)
    print(f"now={now} records={len(recs)}")
    for r in recs[:10]:
        age = now - (r.get("created_at") or 0)
        print(
            f"  id={r['id']:<14} kind={r['kind']:<6} status={r['status']:<11} "
            f"task={str(r.get('task_id'))[:24]:<24} age={age}s"
        )


if __name__ == "__main__":
    main()
