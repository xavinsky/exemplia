# Évaluation

## Évaluation

```bash
uv run python -m exemplia.llmops.evaluer rag service_client
uv run python -m exemplia.llmops.evaluer --recharger service_client workflow
```

Les jeux du service client et du workflow citent des commandes dont le statut détermine le résultat
attendu : ils supposent les données dans leur état initial. Une démonstration qui annule ou retourne
une commande fausse les cas correspondants, d'où `--recharger`, qui régénère les données avant
d'évaluer.

Chaque exemple a un jeu de test, une fonction de prédiction qui appelle le vrai composant, et des
scorers. `mlflow.genai.evaluate` exécute le tout, trace chaque cas et enregistre les métriques dans
l'expérience `evaluation-<exemple>`. Le script affiche ensuite les cas en échec, avec la sortie et
la justification du juge.

La fonction de prédiction est tracée comme span racine (`evaluation.<exemple>`) : les juges
évaluent ses entrées et sorties. Sans ce span, MLflow prend un appel au modèle interne au composant
(un prompt de plusieurs milliers de jetons) et le juge, limité par le contexte du serveur, renvoie
une réponse vide.

Les cas sont évalués un par un (`MLFLOW_GENAI_EVAL_MAX_WORKERS=1` par défaut) : sur un seul GPU, des
cas en parallèle obligent Ollama à alterner sans cesse modèle évalué, modèle de garde et juge en
mémoire.

| Exemple | Jeu | Scorers déterministes | Juges LLM |
|---|---|---|---|
| `service_client` | `evaluation/service_client.jsonl` (12 demandes) | outils attendus appelés, action proposée, escalade | consignes (politesse, pas d'action annoncée comme faite, pas de geste commercial, hors sujet décliné) |
| `rag` | `evaluation/rag.jsonl` (13 questions) | rappel des documents attendus, aucune fuite d'accès, présence ou absence de citations | `Correctness` (faits attendus) |
| `conformite` | `evaluation/conformite.jsonl` (3 contrats) | verdicts corrects par règle, citations vérifiées | — |
| `analyse_donnees` | `evaluation/analyse_donnees.jsonl` (10 questions) | requête exécutée, résultat identique à la requête de référence | — |
| `garde` | `evaluation/garde.jsonl` (20 messages) | blocage correct (attaques et messages légitimes) | — |
| `workflow` | `workflow_agents/emails.py` × 2 architectures | action proposée, escalade, nombre d'appels LLM | consignes sur le brouillon |

Principes :

- **Le code vérifie tout ce qui peut l'être** : outil appelé, verdict, résultat SQL. Ces scorers
  sont gratuits et reproductibles. Les juges ne servent qu'à ce que le code ne sait pas mesurer.
- **Le juge est un autre modèle** que celui évalué (`IACU_MODELE_JUGE`), désigné par
  `uri_juge()` au format MLflow (`ollama:/gemma4:12b`), avec les mêmes options d'inférence que le
  reste du projet (`parametres_juge()`).
- Pour l'analyse de données, le résultat attendu est recalculé sur la base à chaque évaluation à
  partir de la requête de référence : le jeu reste valable si les données sont rechargées.
- Un scorer qui renvoie `None` est ignoré pour ce cas (expectation absente).
- MLflow refuse une expectation de valeur nulle : l'absence d'action attendue s'écrit `"aucune"`.

Comparer deux configurations : changer le modèle ou le prompt, relancer l'évaluation, comparer les
deux runs dans l'interface MLflow.

## Résultats de référence

Modèles par défaut (`qwen3.5:9b`, juge `gemma4:12b`, modération `llama-guard3:8b`,
embeddings `qwen3-embedding:0.6b`), GPU de 12 Go :

| Exemple | Résultats | Durée |
|---|---|---|
| `garde` | blocage correct 0,90 (0 faux positif sur 11 messages légitimes) | < 1 min |
| `rag` | rappel 1,0 · aucune fuite d'accès · citations 1,0 · exactitude (juge) 0,92 | ~8 min |
| `service_client` | consignes (juge) 1,0 · mentions 1,0 · action 0,92 · escalade 0,91 · outils 0,80 | ~10 min |
| `conformite` | 3 contrats, 21 verdicts : verdicts corrects 0,90 · citations vérifiées 0,95 | ~1 min |
| `analyse_donnees` | requête exécutée 1,0 · résultat identique à la référence 1,0 | ~2 min |
| `workflow` | action 1,0 · escalade 1,0 · brouillon (juge) 1,0 ; 2,1 appels LLM (workflow) contre 5,0 (orchestrateur) | ~12 min |

Le juge est le poste le plus lent (10 à 55 s par jugement).
