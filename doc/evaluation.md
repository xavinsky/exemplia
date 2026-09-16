# Évaluation et résultats

## Tests

| Niveau | Contenu | Besoin |
|---|---|---|
| Unitaires | Outils, règles, validations SQL, garde (règles), génération de données, sélection des passages de contrat | Aucun service |
| Intégration sans modèle | Routes FastAPI et workflows avec `FauxClientLLM` | Aucun service |
| Évaluation | Jeux JSONL avec les modèles réels, résultats dans MLflow | Ollama (GPU), Qdrant, PostgreSQL |

`make tests` exécute les deux premiers niveaux :

```bash
make tests
```

Le client LLM y est remplacé par un faux client scripté, la base par SQLite en mémoire, Qdrant par
son mode mémoire, MLflow par un stockage SQLite temporaire. Ils couvrent la plomberie : outils,
règles métier, garde, validation SQL, workflows LangGraph, routes web, cycle MLOps, mécanique
d'évaluation. L'intégration continue
(`.github/workflows/ci.yml`) les rejoue à chaque push, avec `ruff`.

La qualité des réponses des modèles se mesure à part, avec `make evaluer`, qui demande les modèles
et les services. La mécanique — jeux, scorers, juges, surveillance — est décrite dans
[llmops](../src/exemplia/llmops/README.md).

## Résultats mesurés

Avec les modèles par défaut :

| Exemple | Résultats |
|---|---|
| Garde | blocage correct 0,90 sur 20 messages, aucun faux positif sur les 11 messages légitimes |
| RAG | 13 questions : rappel 1,0 · aucune fuite d'accès · citations 1,0 · exactitude (juge) 0,92 |
| Service client | 13 demandes : consignes (juge) 1,0 · mentions 1,0 · action 0,92 · escalade 0,91 · outils 0,80 |
| Conformité | 3 contrats, 21 verdicts : verdicts corrects 0,90 · citations vérifiées 0,95 |
| Analyse de données | 10 questions : requête exécutée 1,0 · résultat identique à la référence 1,0 |
| Workflow d'agents | 7 emails × 2 architectures : action 1,0 · escalade 1,0 · brouillon 1,0 ; 2,1 appels LLM contre 5,0 pour l'orchestrateur |
| Tri des tickets | LLM 1,000 (300 ms) · CamemBERT 0,935 (0,26 ms) · embeddings 0,864 (6,6 ms) · TF-IDF 0,769 (0,02 ms) |

Ces scores varient de quelques points d'une exécution à l'autre : le serveur de modèles n'est pas
déterministe d'un lot à l'autre, et le juge non plus.
