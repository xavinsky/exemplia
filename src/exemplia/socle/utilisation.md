# Comment utiliser ?

## Fichiers

| Fichier | Rôle |
|---|---|
| `config.py` | Paramètres `IACU_*` lus depuis l'environnement et `.env` (modèles, URL des services) |
| `llm.py` | Client LLM : `discuter` (conversation et appels d'outils), `extraire` (sortie structurée Pydantic), `vectoriser` (embeddings) |
| `base_donnees.py` | Schéma SQLAlchemy Core de l'Entreprise Exemple, moteur applicatif et moteur en lecture seule |
| `entreprise.py` | Génération déterministe des données et chargement (`uv run exemplia-donnees`) |
| `documents.py` | Lecture des documents Markdown et de leur niveau d'accès |
| `tracage.py` | Activation des traces MLflow |
| `web.py`, `templates/`, `static/` | Gabarit HTML, feuille de style, catalogue des exemples, dépendances FastAPI |
| `explications.py` | Section « Comment ça marche ? » de chaque exemple, rendue depuis son Markdown |

## Charger les données

```bash
uv run exemplia-donnees                          # recharge les données de l'Entreprise Exemple
uv run exemplia-donnees --reference 2026-01-15   # dates calculées par rapport à ce jour
```

Les paramètres `IACU_*` se posent dans l'environnement ou dans `.env` (modèle `.env.example`).
