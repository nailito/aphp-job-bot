"""
debug_signature.py
Lance ce script pour trouver où la signature est cachée dans le HTML de la homepage.
"""
import re
import requests

BASE_URL = "https://chu-lyon.nous-recrutons.fr"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}

resp = requests.get(BASE_URL + "/", headers=HEADERS, timeout=30)
html = resp.text

print(f"=== HTML reçu : {len(html)} caractères ===\n")

# 1. Chercher toutes les occurrences du mot "signature"
matches = [(m.start(), html[max(0,m.start()-100):m.start()+200])
           for m in re.finditer(r'signature', html, re.I)]

print(f"Occurrences de 'signature' : {len(matches)}\n")
for i, (pos, ctx) in enumerate(matches[:10]):
    print(f"--- Occurrence {i+1} (pos {pos}) ---")
    print(repr(ctx))
    print()

# 2. Chercher les hashes hexadécimaux longs (32+ chars)
hashes = re.findall(r'[a-f0-9]{32,}', html)
print(f"\nHashes hex 32+ chars trouvés : {len(hashes)}")
for h in hashes[:10]:
    print(f"  {h}")

# 3. Chercher "jet_engine" dans les scripts
jet_matches = [(m.start(), html[max(0,m.start()-50):m.start()+300])
               for m in re.finditer(r'jet.?engine', html, re.I)]
print(f"\nOccurrences jet_engine : {len(jet_matches)}")
for i, (pos, ctx) in enumerate(jet_matches[:3]):
    print(f"--- {i+1} ---")
    print(repr(ctx))
    print()

# 4. Sauvegarder le HTML complet pour inspection manuelle
with open("homepage_hcl.html", "w", encoding="utf-8") as f:
    f.write(html)
print("\n✅ HTML complet sauvegardé dans homepage_hcl.html")