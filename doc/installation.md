# Installation et exécution

Prérequis : Python 3.12, [uv](https://docs.astral.sh/uv/), Docker, [Ollama](https://ollama.com).

## Mise en route

```bash
make setup      # dépendances, services Docker, modèles Ollama, données de l'entreprise et index
make setup-cpu  # la même chose sans GPU (sans PyTorch)
make start      # application web sur http://127.0.0.1:8000
make stop       # arrête les services ; les données restent dans les volumes Docker
```

`make setup` enchaîne :

1. `uv sync --group gpu` — le groupe `gpu` apporte PyTorch et transformers ;
2. copie de `.env.example` vers `.env` s'il n'existe pas ;
3. `docker compose up -d --wait` — PostgreSQL, Qdrant et MLflow (interface sur http://localhost:5000) ;
4. `ollama pull` des quatre modèles par défaut ;
5. `exemplia-donnees` — création du schéma et des données de l'Entreprise Exemple ;
6. `exemplia.rag.indexer` — index documentaire dans Qdrant.

`make setup-cpu` fait la même chose avec `uv sync` seul, sans le groupe `gpu` : tout fonctionne,
sauf le fine-tuning de CamemBERT (`make experiences`) et le classifieur d'injection de la garde.

## Modèles par défaut

Cible matérielle de référence : GPU de 12 Go de VRAM, 30 Go de RAM. Tous configurables dans `.env` :

| Usage | Modèle | Taille Q4 | Service |
|---|---|---|---|
| Conversation, outils, extraction | `qwen3.5:9b` | 6,6 Go | Ollama |
| Juge (garde de sortie, évaluation) | `gemma4:12b` | 7,6 Go | Ollama |
| Modération | `llama-guard3:8b` | 4,9 Go | Ollama |
| Embeddings | `qwen3-embedding:0.6b` | < 1 Go | Ollama |
| Sparse (BM25) et reranking | `Qdrant/bm25`, `jinaai/jina-reranker-v2-base-multilingual` | — | fastembed (ONNX, CPU) |
| Fine-tuning de classification | `almanach/camembert-base` | — | transformers (GPU) |
| Cloud | `gemini-3.8-flash` | — | Vertex AI |

Le juge est volontairement un modèle différent de celui qui répond : un modèle qui se juge lui-même
est biaisé. Contrepartie sur 12 Go de VRAM, les deux ne tiennent pas ensemble en mémoire : Ollama
les alterne, ce qui ajoute une latence de chargement quand le juge sert de filtre en ligne.

Le serveur Ollama doit laisser au moins 4 096 jetons de contexte (valeur par défaut) : au-delà, les
prompts sont tronqués sans erreur. L'API compatible OpenAI ne permet pas de régler ce contexte par
requête ; il se fixe sur le serveur (`OLLAMA_CONTEXT_LENGTH`). Le plus gros prompt des exemples —
celui du service client, qui embarque les CGV, la politique de retour et la FAQ — mesure environ
1 400 jetons.

## GPU plus petit

Les quatre modèles se remplacent dans `.env`, sans toucher au code :

```bash
IACU_MODELE_CHAT=qwen3.5:4b
IACU_MODELE_JUGE=gemma3:4b
IACU_MODELE_GARDE=llama-guard3:1b
IACU_MODELE_EMBEDDINGS=qwen3-embedding:0.6b
```

Pour dimensionner : la taille affichée par `ollama list`, ou sur `ollama.com/library/<modèle>/tags`,
est celle des poids en VRAM — compter environ 0,6 à 0,75 Go par milliard de paramètres en
quantification Q4, plus quelques centaines de mégaoctets pour le contexte. Ollama garde plusieurs
modèles chargés tant qu'ils tiennent, et décharge le plus ancien sinon : ce qui compte, c'est la
somme des modèles utilisés dans le même écran.

| VRAM | Conversation | Juge | Modération | Embeddings |
|---|---|---|---|---|
| 12 Go | `qwen3.5:9b` (6,6 Go) | `gemma4:12b` (7,6 Go) | `llama-guard3:8b` (4,9 Go) | `qwen3-embedding:0.6b` (0,6 Go) |
| 8 Go | `qwen3.5:4b` | `gemma3:4b` | `llama-guard3:1b` (1,6 Go) | `qwen3-embedding:0.6b` |
| 6 Go | `qwen3.5:2b` | `qwen3.5:4b` | `llama-guard3:1b` | `qwen3-embedding:0.6b` |

Les familles disponibles chez Ollama : `qwen3.5` en 0.8b, 2b, 4b, 9b et au-delà ; `gemma4` à partir
de 12b, `gemma3` en 1b, 4b, 12b et 27b ; `llama-guard3` en 1b et 8b. Garder un juge différent du
modèle de conversation, même petit. Les scores de [l'évaluation](evaluation.md) sont mesurés avec
les modèles par défaut : un modèle plus petit répond et juge moins bien, et l'évaluation le montre.

Trois réglages du serveur Ollama aident quand la VRAM est juste :

| Variable | Effet |
|---|---|
| `OLLAMA_MAX_LOADED_MODELS=1` | Un seul modèle en mémoire à la fois : plus de chargements, aucun dépassement |
| `OLLAMA_KEEP_ALIVE=30m` | Garde le modèle chargé entre deux requêtes, au lieu des 5 minutes par défaut |
| `OLLAMA_CONTEXT_LENGTH=4096` | Contexte alloué par modèle chargé ; l'augmenter consomme de la VRAM |

Ce qui ne tient pas en VRAM est réparti sur le processeur par Ollama : l'exemple répond quand même,
plus lentement. `make setup-cpu` installe la même chose sans PyTorch, pour une machine sans carte
graphique du tout.

## Autres cibles

```bash
make tests          # pytest, ruff check et ruff format --check
make experiences    # tri des tickets : compare les approches, entraîne CamemBERT, promeut le champion
make evaluer        # évaluations sur les jeux de test, résultats dans MLflow
make surveillance   # note un échantillon des traces récentes de l'application
```

`make evaluer` régénère les données avant de mesurer (`--recharger`) : certains jeux de test
supposent l'état initial des commandes. Les cibles s'appuient sur les modules
`exemplia.tri_tickets.experiences`, `exemplia.tri_tickets.fine_tuning`, `exemplia.llmops.evaluer` et
`exemplia.llmops.surveillance`, qui acceptent d'autres options en `uv run python -m ...`.

L'exemple cloud se lance à part, avec un projet GCP facturable :

```bash
gcloud auth application-default login
IACU_GCP_PROJET=mon-projet uv run python -m exemplia.vertex_gemini.exemple
```
