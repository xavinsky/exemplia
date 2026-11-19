# Comment utiliser ?

## Lancer

```bash
gcloud auth application-default login
IACU_GCP_PROJET=mon-projet uv run python -m exemplia.vertex_gemini.exemple
```

| Paramètre | Défaut |
|---|---|
| `IACU_GCP_PROJET` | aucun (obligatoire) |
| `IACU_GCP_REGION` | `europe-west1` |
| `IACU_MODELE_VERTEX` | `gemini-3.8-flash` |

L'identifiant exact du modèle et sa disponibilité dans la région se vérifient dans Vertex AI Model
Garden.
