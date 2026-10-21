"""Inject a job record with a real Agnes task id, then read it back via the API.

Verifies the 202/job read path end-to-end without waiting for a free video queue:
the job should transition to completed and get a persisted local file.

Usage: python scripts/simulate_job_completion.py <agnes_task_id>
"""

import sys
import time

import httpx

from app import history

BASE = "http://127.0.0.1:8000"


def main() -> int:
    task_id = sys.argv[1] if len(sys.argv) > 1 else "task_mglLKENzGFzH1Dmaqu8bE06A1xE9WtEW"
    rec = history.add_record(
        "video",
        status="queued",
        task_id=task_id,
        prompt="simulated job for read-path verification",
        model="agnes-video-2.5-flash",
        size="720P",
        seconds=4,
        aspect_ratio="16:9",
        ui_mode="img2vid",
    )
    print(f"[1] injected job {rec['id']} -> agnes task {task_id}")

    c = httpx.Client(transport=httpx.HTTPTransport(proxy=None), timeout=120)
    for i in range(6):
        r = c.get(f"{BASE}/api/jobs/{rec['id']}")
        j = r.json()
        print(
            f"[2] t+{i * 5}s HTTP {r.status_code} status={j.get('status')} "
            f"task_id={j.get('task_id')} local_url={j.get('local_url')}"
        )
        if j.get("status") in ("completed", "failed"):
            break
        time.sleep(5)

    stored = history.get_record(rec["id"])
    print(f"[3] persisted record: status={stored.get('status')} local_url={stored.get('local_url')}")
    ok = stored.get("status") == "completed" and bool(stored.get("local_url"))
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
