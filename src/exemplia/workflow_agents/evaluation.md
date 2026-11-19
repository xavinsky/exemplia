# Évaluation

## Évaluation

`uv run python -m exemplia.llmops.evaluer workflow` exécute chaque email avec les deux
architectures jusqu'à la validation humaine : action proposée, escalade, nombre d'appels LLM et juge
sur le brouillon.

Avec `qwen3.5:9b`, sur les 7 emails d'exemple :

| | Workflow déterministe | Agent orchestrateur |
|---|---|---|
| Action correcte | 1,00 | 1,00 |
| Escalade correcte | 1,00 | 1,00 |
| Consignes du brouillon (juge) | 1,00 | 1,00 |
| Appels LLM par email | 2,1 | 5,0 |

Même résultat métier, pour 2,4 fois plus d'appels au modèle côté orchestrateur : c'est le compromis
coût contre souplesse. Sur ces demandes, dont le déroulé est connu, le workflow déterministe est le
bon choix ; l'orchestrateur garde l'avantage sur des demandes qu'on ne peut pas figer.
