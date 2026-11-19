# RAG documentaire

![Capture de la page RAG documentaire](../../../captures/rag.png)

Questions en langage naturel sur les documents de l'entreprise, avec réponse citée et filtrage par
niveau d'accès.

## Besoin

Quand la base documentaire dépasse ce qu'on peut mettre dans un prompt, on récupère d'abord les
passages pertinents, puis le LLM répond à partir d'eux seuls. En entreprise, trois exigences
s'ajoutent à la version de démonstration habituelle :

- **droits d'accès** : un collaborateur ne doit pas obtenir, même reformulé, le contenu d'un
  document qu'il n'a pas le droit de lire ;
- **vérifiabilité** : chaque affirmation renvoie à sa source ;
- **honnêteté** : « je ne trouve pas » plutôt qu'une réponse inventée.

## Limites

- Le premier appel au BM25 et au reranker télécharge leurs modèles depuis Hugging Face.
- Documents Markdown uniquement.
- La détection des passages modifiés compare le texte stocké dans Qdrant : elle ne voit pas un
  changement de modèle d'embeddings ou de paramètres de découpage, qui demandent `--reconstruire`.

La suite : [Comment ça marche ?](comment-ca-marche.md) · [Comment utiliser ?](utilisation.md) · [Évaluation](evaluation.md).
