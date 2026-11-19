# Fonctionnement

## Composants

```mermaid
flowchart TD
  classDef externe fill:#fed7aa,stroke:#ea580c,color:#7c2d12
  classDef code fill:#ffffff,stroke:#6b7280,color:#1f2937
  classDef gpu fill:#fecaca,stroke:#dc2626,color:#7f1d1d
  classDef disque fill:#dcfce7,stroke:#16a34a,color:#14532d

  Term["terminal<br/>uv run python -m<br/>exemplia.llmops.evaluer rag"]
  Jeux[("evaluation/*.jsonl<br/>inputs, expectations")]
  subgraph Py["Processus Python : python -m exemplia.llmops.…"]
    Eval["evaluer.py<br/>main, EXEMPLES"]
    Evaluate["mlflow.genai.evaluate<br/>un cas à la fois"]
    Comp["composant évalué<br/>predire : RAG, assistant,<br/>analyste, garde, graphes"]
    Scor["scorers.py<br/>scorers déterministes"]
    Juges["juges MLflow<br/>Correctness, Guidelines,<br/>Safety"]
    Surv["surveillance.py<br/>--heures, --max, --exemple"]
  end
  Donnees[("PostgreSQL, Qdrant<br/>conteneurs Docker")]
  Ollama["Ollama (hôte)<br/>qwen3.5:9b, llama-guard3:8b<br/>gemma4:12b, embeddings"]
  MLflow[("MLflow<br/>conteneur Docker")]

  Term -- "① lancement CLI<br/>exemples, options" --> Eval
  Eval -. "② SQL, option recharger<br/>données régénérées" .-> Donnees
  Jeux -- "③ lecture<br/>charger_jeu" --> Eval
  Eval -- "④ HTTP REST<br/>expérience, run, params" --> MLflow
  Eval -- "⑤ appel Python<br/>data, predict_fn, scorers" --> Evaluate
  Evaluate -- "⑥ appel Python<br/>predire avec inputs" --> Comp
  Comp -- "⑦ SQL, HTTP<br/>commandes, passages" --> Donnees
  Comp -- "⑧ HTTP POST<br/>/v1/chat/completions,<br/>/v1/embeddings" --> Ollama
  Evaluate -- "⑨ appel Python<br/>outputs, expectations" --> Scor
  Evaluate -- "⑩ ⑮ appel Python<br/>entrées, sorties" --> Juges
  Juges -- "⑪ ⑯ HTTP POST<br/>/v1/chat/completions" --> Ollama
  Evaluate -- "⑫ ⑰ HTTP REST<br/>traces, scores, métriques" --> MLflow
  Surv -. "⑬ HTTP REST<br/>search_traces" .-> MLflow
  Surv -. "⑭ appel Python<br/>traces, scorers" .-> Evaluate

  class Term,Eval,Evaluate,Comp,Scor,Juges,Surv code
  class Ollama gpu
  class Jeux,Donnees,MLflow disque
```

Les étapes ① à ⑫ sont une évaluation, `python -m exemplia.llmops.evaluer <exemple>`, répétées pour chaque exemple demandé. Les étapes ⑬ à ⑰ sont la surveillance, `python -m exemplia.llmops.surveillance`, lancée séparément ; elle réutilise `mlflow.genai.evaluate` et les juges.

- **① Lancement.** `evaluer.main` reçoit un ou plusieurs exemples parmi `EXEMPLES` (`service_client`, `rag`, `conformite`, `analyse_donnees`, `garde`, `workflow`) et l'option `--recharger`. Il fixe `MLFLOW_GENAI_EVAL_MAX_WORKERS=1` et active `mlflow.openai.autolog()`.
- **② Rechargement.** Avec `--recharger`, `entreprise.charger(moteur(), entreprise.generer())` régénère les données de l'entreprise dans PostgreSQL, pour que les commandes citées par les jeux retrouvent leur statut initial.
- **③ Jeu de test.** `charger_jeu` lit `evaluation/<exemple>.jsonl`, une ligne `{"inputs", "expectations"}` par cas. Pour `analyse_donnees`, `_jeu_analyse` exécute en plus chaque `sql_reference` sur la base en lecture seule et ajoute le résultat aux attentes. Le jeu du workflow est construit depuis `workflow_agents/emails.py`, chaque email étant évalué avec les deux architectures.
- **④ Run.** Pour chaque exemple, `mlflow.set_experiment("evaluation-<exemple>")` puis un run nommé `<exemple>-<modèle de chat>`, avec en paramètres `modele_chat`, `modele_juge` et `modele_embeddings`.
- **⑤ Évaluation.** La fonction `evaluer_<exemple>` construit le vrai composant avec `client_par_defaut()` et renvoie `predire` et la liste des scorers. `predire` est enveloppée dans `mlflow.trace(name="evaluation.<exemple>")` pour servir de span racine, puis passée à `mlflow.genai.evaluate` avec le jeu.
- **⑥ Prédiction.** Pour chaque cas, `predire(**inputs)` appelle le composant (`RAG.repondre`, `AssistantServiceClient.repondre`, `Analyste.repondre`, `AnalyseurConformite.analyser`, `Garde.verifier_entree`, graphe LangGraph) et renvoie un dictionnaire de sorties : réponse, outils appelés, action proposée, documents retenus, SQL, verdicts…
- **⑦ Données.** Le composant lit ce dont il a besoin : commandes et tables en SQL dans PostgreSQL (service client, analyse de données, workflow), passages par HTTP dans Qdrant pour le RAG, dont le reranker ONNX tourne dans le processus. La conformité lit ses contrats dans `data/entreprise/documents`.
- **⑧ Modèles du composant.** Les appels passent par `ClientOpenAICompatible` vers `IACU_LLM_BASE_URL` : modèle de chat `qwen3.5:9b`, modération `llama-guard3:8b` et juge de sortie `gemma4:12b` quand la garde du composant les inclut, embeddings `qwen3-embedding:0.6b` pour la recherche du RAG.
- **⑨ Scorers déterministes.** Chaque scorer `@scorer` de `scorers.py` compare `outputs` aux `expectations` du cas et renvoie un booléen, une fraction, un compte (`appels_llm`) ou `None` quand l'attente correspondante est absente.
- **⑩ Juges.** `exactitude()` (`Correctness`, RAG) et `consignes()` (`Guidelines`, service client et workflow) reçoivent les entrées et sorties du span racine. Leur modèle est `uri_juge()`, soit `ollama:/gemma4:12b`, avec `parametres_juge()` (`reasoning_effort` repris de `IACU_LLM_REFLEXION`).
- **⑪ Appel au juge.** L'adaptateur de MLflow pour le fournisseur `ollama` envoie une requête Chat Completions à `http://localhost:11434/v1`, son adresse par défaut, indépendante de `IACU_LLM_BASE_URL`. Le juge renvoie une valeur (`yes`/`no`) et une justification.
- **⑫ Enregistrement.** Les traces de chaque cas, avec les appels au modèle captés par l'autolog, les valeurs des scorers et les métriques agrégées vont dans le run. Le script affiche ensuite les métriques, les moyennes par architecture pour le workflow, et les cas en échec avec leur sortie et la justification du juge.
- **⑬ Traces de production.** `surveillance.py` interroge l'expérience `exemplia` : traces au statut `OK` des dernières `--heures` (24), au plus `--max` (50), éventuellement filtrées sur le tag `exemple`. Seules les traces qui portent ce tag sont gardées.
- **⑭ Évaluation sans référence.** Les traces sont passées comme données à `mlflow.genai.evaluate`, sans fonction de prédiction, dans l'expérience `surveillance`, avec deux juges : `consignes_production` (`Guidelines` sur trois règles) et `Safety`.
- **⑮ ⑯ Juges sur les traces**, par le même chemin que ⑩ et ⑪.
- **⑰ Enregistrement** des scores dans un run `traces-<heures>h` de l'expérience `surveillance`, avec le nombre de traces en paramètre.

**Ce que fait le GPU.** Tout le calcul de modèles passe par Ollama : génération et appels d'outils du composant évalué (⑧), modération, embeddings, puis génération de chaque jugement (⑪, ⑯). Les cas étant évalués un par un, Ollama charge tour à tour le modèle de chat, Llama Guard et le juge dans la mémoire du GPU. Les scorers déterministes, la lecture des jeux et l'agrégation des métriques tournent sur le CPU.

## Traces

Activées par le socle (`socle/tracage.py`) dans l'expérience `exemplia` :

| Source | Contenu |
|---|---|
| Autolog OpenAI | Chaque appel au serveur de modèles : messages, réponse, jetons, latence |
| Autolog LangChain | Nœuds des graphes LangGraph |
| `@mlflow.trace` et spans | Étapes métier : `service_client.repondre`, `rag.recherche_hybride` (RETRIEVER), `rag.rerank` (RERANKER), outils (TOOL), garde (GUARDRAIL) |

Chaque réponse de l'application affiche sa propre trace (appels au modèle, messages envoyés,
durée) et renvoie vers l'onglet « Traces » de l'expérience dans MLflow, où les mêmes échanges
apparaissent avec leurs spans et leurs durées.

Toutes les traces de l'application portent le tag `exemple` ; celles du service client ont aussi
l'utilisateur et la session (`mlflow.trace.user`, `mlflow.trace.session`), celles du workflow
l'architecture et l'identifiant du traitement. Les nœuds des graphes LangGraph sont tracés par
l'autolog sous le span `workflow.executer`.

## Surveillance

```bash
uv run python -m exemplia.llmops.surveillance --heures 24 --max 50 --exemple service_client
```

Échantillonne les traces récentes de l'application et les note avec des juges sans référence
(consignes de production, `Safety`). Les résultats vont dans l'expérience `surveillance`. À planifier
(cron) pour suivre l'évolution dans le temps.

## MLOps du tri des tickets

Le cycle complet (runs comparés, Model Registry, alias `champion`, Prompt Registry) est montré dans
[tri_tickets](../tri_tickets/README.md).
