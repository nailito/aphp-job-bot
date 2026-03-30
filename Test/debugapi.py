"""
debug_rest_api.py
Teste l'API REST WordPress native pour récupérer les offres HCL
sans avoir besoin de signature JetEngine.
"""
import json
import requests

BASE_URL = "https://chu-lyon.nous-recrutons.fr"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

endpoints = [
    "/wp-json/wp/v2/job?per_page=3&_fields=id,title,link,date,content,meta",
    "/wp-json/wp/v2/job?per_page=3",
    "/wp-json/wp/v2/types/job",          # infos sur le post type
    "/wp-json/wp/v2/types",              # liste tous les post types exposés
]

for ep in endpoints:
    url = BASE_URL + ep
    print(f"\n{'='*60}")
    print(f"GET {ep}")
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        print(f"Status : {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list):
                print(f"Nb résultats : {len(data)}")
                if data:
                    first = data[0]
                    print(f"Clés disponibles : {list(first.keys())}")
                    print(f"Exemple id     : {first.get('id')}")
                    print(f"Exemple title  : {first.get('title', {}).get('rendered', '')[:80]}")
                    print(f"Exemple link   : {first.get('link', '')}")
                    # Afficher les meta/acf s'il y en a
                    if first.get('meta'):
                        print(f"meta keys : {list(first['meta'].keys())[:10]}")
                    if first.get('acf'):
                        print(f"acf  keys : {list(first['acf'].keys())[:10]}")
            else:
                print(json.dumps(data, indent=2, ensure_ascii=False)[:500])
        else:
            print(f"Réponse : {r.text[:300]}")
    except Exception as e:
        print(f"Erreur : {e}")