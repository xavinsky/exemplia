# Comment ça marche ?

```
300 tickets étiquetés (5 catégories)
      │ séparation par formulation : le test ne contient que des tournures
      │ absentes de l'entraînement
      ├──► TF-IDF + régression logistique        ─┐
      ├──► embeddings + régression logistique     │  un run MLflow chacun :
      ├──► CamemBERT fine-tuné (GPU)              ├─ F1 macro, exactitude, latence,
      └──► LLM sans exemple, prompt versionné    ─┘  matrice de confusion, modèle
                                │
              promotion : meilleur F1 ; à un point près, le plus rapide gagne
                                │
        Model Registry « tri-tickets » : nouvelle version, alias « champion »
                                │
                 l'application charge models:/tri-tickets@champion
```

## Ce que montre la comparaison

Sur des formulations jamais vues à l'entraînement, le LLM sans exemple classe parfaitement, pour
300 ms par ticket. CamemBERT fine-tuné en quinze secondes atteint 0,935 pour 0,26 ms. Sur un volume
élevé, c'est ce compromis qu'il faut regarder en premier.

Changer de modèle servi ne demande pas de redéploiement : l'alias `champion` se déplace d'une
version à l'autre.

## Briques

| Brique | Rôle |
|---|---|
| scikit-learn | TF-IDF, régression logistique, métriques |
| transformers (GPU) | Fine-tuning de `almanach/camembert-base` |
| Ollama | Embeddings et classification sans exemple |
| MLflow Tracking | Un run par approche, mêmes métriques |
| MLflow Prompt Registry | Prompt de classification versionné, référencé par le modèle |
| MLflow Model Registry | Versions du modèle et alias `champion` |
