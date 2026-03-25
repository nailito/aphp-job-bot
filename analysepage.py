# analyze_pages.py
with open("/workspaces/aphp-job-bot/pages_20260325_225532.txt") as f:
    lines = f.readlines()

counts = [int(l.strip().split(":")[1]) for l in lines if ":" in l]
print(f"Pages avec 0 offres    : {counts.count(0)}")
print(f"Pages avec < 20 offres : {sum(1 for c in counts if 0 < c < 20)}")
print(f"Offres min/max/moy     : {min(counts)} / {max(counts)} / {sum(counts)/len(counts):.1f}")
print(f"Total offres comptées  : {sum(counts)}")