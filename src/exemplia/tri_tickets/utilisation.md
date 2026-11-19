# Comment utiliser ?

## Lancer

```bash
make experiences                                                   # les quatre approches, puis le champion
uv run python -m exemplia.tri_tickets.experiences                  # tfidf, embeddings, llm
uv run python -m exemplia.tri_tickets.experiences --approches tfidf
uv run python -m exemplia.tri_tickets.fine_tuning --promouvoir     # CamemBERT, groupe `gpu`
```

La page `/tri-tickets` classe un ticket avec le modèle de votre choix : le champion, ou n'importe
quelle approche servie depuis son meilleur run. Le même ticket passé dans les quatre montre
l'essentiel en un écran — même catégorie trouvée, trois ordres de grandeur d'écart sur le coût, et
une trace vide pour les approches qui n'appellent aucun serveur.

## Fichiers

| Fichier | Contenu |
|---|---|
| `modeles.py` | Pipeline TF-IDF, modèles pyfunc embeddings et LLM, prompt |
| `experiences.py` | Jeu de données, runs, promotion du champion |
| `fine_tuning.py` | Fine-tuning CamemBERT (groupe `gpu`) |
| `web.py`, `templates/` | Interface |
