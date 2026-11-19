# Évaluation

## Résultats

`qwen3.5:9b` pour le LLM, `qwen3-embedding:0.6b` pour les embeddings, GPU de 12 Go :

| Approche | F1 macro | Exactitude | Latence par ticket |
|---|---|---|---|
| `llm` | 1,000 | 1,000 | 300 ms |
| `camembert` | 0,935 | 0,934 | 0,26 ms |
| `embeddings` | 0,864 | 0,869 | 6,6 ms |
| `tfidf` | 0,769 | 0,770 | 0,02 ms |

Le LLM sans exemple classe parfaitement ces tickets, y compris des formulations jamais vues, et
c'est l'approche la plus lente de trois ordres de grandeur. CamemBERT fine-tuné en 15 secondes sur
239 tickets atteint 0,935 pour une latence négligeable : sur un volume élevé, c'est le compromis à
regarder en premier.

| Élément MLflow | Usage |
|---|---|
| Expérience `tri-tickets` | Un run par approche, mêmes métriques, comparables dans l'interface |
| `mlflow.sklearn.log_model` | Pipeline TF-IDF |
| `mlflow.pyfunc.PythonModel` | Approches qui appellent un serveur (embeddings, LLM) : chargées et appelées comme le modèle scikit-learn |
| `mlflow.transformers.log_model` | CamemBERT fine-tuné |
| Prompt Registry | Prompt de classification du LLM (`tri-tickets-zero-shot`), référencé par URI dans le modèle |
| Model Registry, alias | `champion` désigne la version servie : changer de modèle = déplacer l'alias, sans redéployer l'application |

La page renvoie vers chaque point d'intégration : l'expérience et ses runs, la comparaison des
quatre runs, le Model Registry avec l'alias `champion`, et le Prompt Registry. Le nom d'une approche
ouvre son propre run (paramètres, métriques, matrice de confusion, modèle enregistré). Les
identifiants sont lus dans MLflow au moment de l'affichage : rien n'est stocké, et les liens suivent
les expériences rejouées.

La sélection des paramètres et des métriques de la page de comparaison n'est pas transmissible par
l'URL — MLflow la garde dans l'état du composant — il reste donc à cocher `exactitude` et
`latence_ms_par_ticket` à la main pour montrer le compromis.

La règle de promotion privilégie le modèle le plus rapide à qualité équivalente : un modèle
classique aussi bon qu'un LLM coûte bien moins cher à servir.

## Deux tickets qui séparent les approches

La page propose deux tickets dont le classement diffère d'une approche à l'autre, vérifiés sur les
modèles entraînés. Chaque essai est une ligne — un bouton qui choisit le modèle et remplit le
ticket — et le bouton orange désigne le modèle qui se trompe.

| Ticket | Attendu | tfidf | embeddings | camembert | llm |
|---|---|---|---|---|---|
| « Le colis est bien là, mais la notice annonce un autre modèle. » | produit | livraison | retour | livraison | **produit** |
| « Ma commande est bien arrivée, mais je souhaite la renvoyer. » | retour | livraison | **retour** | **retour** | **retour** |

Le premier demande de comprendre que le sujet est la notice, pas le colis : seul le LLM y arrive.
Le second suffit à tromper TF-IDF, qui compte les mots et voit « commande arrivée », là où les
représentations vectorielles saisissent l'intention.
