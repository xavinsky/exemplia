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

La suite : [Comment ça marche ?](fonctionnement.md) · [Comment utiliser ?](utilisation.md).
