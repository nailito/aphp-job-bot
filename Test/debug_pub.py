import requests, json

resp = requests.get(
    "https://chu-lyon.nous-recrutons.fr/wp-json/wp/v2/job",
    params={"slug": "mqk0warfn2-manipulateur-delectroradiologie-medicale-hopital-lpradel-ghe", "_fields": "id,date,modified,meta"},
    headers={"Accept": "application/json"},
)
print(json.dumps(resp.json(), indent=2, ensure_ascii=False))

print('hello')