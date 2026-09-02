# Contribuer

Merci de proposer les changements dans une branche dédiée et d'ouvrir une pull request courte.

## Installation de développement

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

## Vérifications

```bash
ruff check .
pytest
```

N'ajoutez jamais de fichier `.env`, de profil candidat, de données collectées, de logs ou de
sauvegarde de base de données. Les tests doivent utiliser des données synthétiques.
