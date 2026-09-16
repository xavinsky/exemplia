# Vertex AI + Gemini

Appel minimal d'un modèle Gemini sur Vertex AI : une génération simple et une sortie structurée.

## Quand utiliser un modèle cloud

| Besoin | Local | Cloud |
|---|---|---|
| Données qui ne doivent pas quitter l'infrastructure | oui | selon le contrat et la région |
| Qualité maximale, raisonnement long, grands contextes | limité par la VRAM | oui |
| Coût prévisible à fort volume | oui (matériel amorti) | paiement à l'usage |
| Démarrage sans matériel | non | oui |

Avec le SDK `google-genai`, passer d'un exemple local à Gemini ne change que le client : les
messages, les schémas Pydantic et les règles de garde restent les mêmes.

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

## Points clés

- Authentification par Application Default Credentials : aucune clé dans le code ni dans `.env`.
- Sortie structurée : `response_mime_type="application/json"` et `response_schema` (classe
  Pydantic), résultat dans `reponse.parsed`.
- Consommation : `usage_metadata` donne les jetons d'entrée et de sortie, à suivre pour le coût.

Aucun test automatisé n'appelle ce script : le service est payant.
