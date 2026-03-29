import time
from datetime import datetime

# 👉 adapte cet import à ton projet
# ex: from scraper import scrape_jobs
from scraper import scrape_jobs


class JobMemory:
    def __init__(self, max_missing=3):
        self.jobs = {}  # job_id -> data
        self.max_missing = max_missing

    def update(self, current_jobs):
        now = datetime.utcnow().isoformat()

        current_ids = set()
        new_jobs = []
        seen_jobs = []
        recovered_jobs = []

        # --- Update / insert ---
        for job in current_jobs:
            jid = job["id"]
            current_ids.add(jid)

            if jid not in self.jobs:
                # new job
                self.jobs[jid] = {
                    "data": job,
                    "first_seen": now,
                    "last_seen": now,
                    "missing_count": 0,
                }
                new_jobs.append(jid)
            else:
                # existing job
                if self.jobs[jid]["missing_count"] > 0:
                    recovered_jobs.append(jid)

                self.jobs[jid]["last_seen"] = now
                self.jobs[jid]["missing_count"] = 0
                seen_jobs.append(jid)

        # --- Handle missing ---
        lost_candidates = []
        deleted_jobs = []

        for jid in list(self.jobs.keys()):
            if jid not in current_ids:
                self.jobs[jid]["missing_count"] += 1

                if self.jobs[jid]["missing_count"] == 1:
                    lost_candidates.append(jid)

                if self.jobs[jid]["missing_count"] >= self.max_missing:
                    deleted_jobs.append(jid)
                    del self.jobs[jid]

        return {
            "new": new_jobs,
            "seen": seen_jobs,
            "recovered": recovered_jobs,
            "lost_candidates": lost_candidates,
            "deleted": deleted_jobs,
            "total_tracked": len(self.jobs),
        }


def test_with_memory(n_runs=5, sleep_time=2, max_missing=3):
    memory = JobMemory(max_missing=max_missing)

    for i in range(n_runs):
        print(f"\n=== RUN {i+1}/{n_runs} ===")

        try:
            jobs = scrape_jobs()
        except Exception as e:
            print(f"[ERROR] scrape_jobs failed: {e}")
            continue

        print(f"[INFO] scraped jobs: {len(jobs)}")

        stats = memory.update(jobs)

        print("\n--- STATS ---")
        print(f"New jobs: {len(stats['new'])}")
        print(f"Recovered jobs: {len(stats['recovered'])}")
        print(f"Seen (stable): {len(stats['seen'])}")
        print(f"Missing (1st time): {len(stats['lost_candidates'])}")
        print(f"Deleted (>= {max_missing} misses): {len(stats['deleted'])}")
        print(f"Total tracked: {stats['total_tracked']}")

        # debug samples
        if stats["new"]:
            print(f"Sample NEW: {stats['new'][:10]}")

        if stats["lost_candidates"]:
            print(f"Sample MISSING: {stats['lost_candidates'][:10]}")

        if stats["deleted"]:
            print(f"Sample DELETED: {stats['deleted'][:10]}")

        time.sleep(sleep_time)


if __name__ == "__main__":
    test_with_memory(
        n_runs=5,       # nombre de runs consécutifs
        sleep_time=2,   # pause entre runs
        max_missing=3   # tolérance avant suppression
    )