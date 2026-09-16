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

## Fonctionnement

Le déroulé, diagramme compris, est dans [Comment ça marche ?](comment-ca-marche.md) — le
texte que la page affiche.

| Étape | Choix | Raison |
|---|---|---|
| Découpage | Par section Markdown, puis par paragraphes au-delà de 900 caractères, chevauchement d'un paragraphe | Les sections sont des unités de sens ; le titre du document et de la section est ajouté au texte indexé |
| Identifiant de passage | `document#section#rang-dans-la-section` | Ajouter ou retirer une section ne renomme pas les autres : l'indexation ne retraite que ce qui a changé |
| Recherche hybride | Dense + BM25, fusion RRF dans Qdrant | Le dense trouve les reformulations, le BM25 les termes exacts (« R5 », « article 28 ») |
| Filtre d'accès | Dans la requête Qdrant (`MatchAny` sur `acces`) | Un passage interdit n'est jamais récupéré, donc jamais envoyé au LLM ni tracé |
| Reranking | Cross-encoder multilingue (fastembed, CPU), seuil optionnel | Lit question et passage ensemble : plus précis que la fusion pour ordonner les candidats |
| Génération | Sources numérotées et délimitées, citations `[n]` obligatoires | Vérifiable, et le contenu des documents est traité comme une donnée |
| Citations | Les numéros inexistants sont retirés par le code | Le modèle peut citer une source qui n'existe pas |
| Non-réponse | La phrase imposée par le prompt est exclue du contrôle de fuite | Sans cela, la garde bloque « Je ne trouve pas cette information… », qui est la bonne réponse |

Niveaux d'accès : `public` ⊂ `interne` ⊂ `confidentiel`.

## Lancer

```bash
docker compose up -d qdrant
uv run python -m exemplia.rag.indexer                 # met l'index à jour
uv run python -m exemplia.rag.indexer --reconstruire  # repart d'un index vide
uv run exemplia                                       # page /rag
```

Par défaut, l'indexation est incrémentale : elle ne vectorise que les passages nouveaux ou modifiés
et retire ceux qui ont disparu des documents (`synchroniser`). `--reconstruire` sert après un
changement de modèle d'embeddings ou de découpage, qui rend l'index existant incohérent.

La page propose des questions d'exemple. Poser la question sur le geste commercial en `public` puis
en `interne` montre le filtrage : la réponse n'est disponible qu'au niveau interne. La table des
passages récupérés affiche les scores de fusion et de reranking.

## Évaluation

`uv run python -m exemplia.llmops.evaluer rag` : rappel des documents attendus, absence de fuite
d'accès, citations présentes (ou absentes pour une question sans réponse), et `Correctness` du juge
sur les faits attendus.

Avec `qwen3-embedding:0.6b`, `qwen3.5:9b` et le reranker Jina, sur 13 questions : rappel des
documents 1,0, aucune fuite d'accès, citations 1,0, exactitude (juge) 0,92 — le point manquant est
une réponse correcte mais incomplète, qui omet un des faits attendus.

## Limites

- Le premier appel au BM25 et au reranker télécharge leurs modèles depuis Hugging Face.
- Documents Markdown uniquement.
- La détection des passages modifiés compare le texte stocké dans Qdrant : elle ne voit pas un
  changement de modèle d'embeddings ou de paramètres de découpage, qui demandent `--reconstruire`.

## Fichiers

| Fichier | Contenu |
|---|---|
| `decoupage.py` | Découpage en passages |
| `index.py` | Index hybride Qdrant, encodeurs BM25, reranker |
| `pipeline.py` | Garde, sélection, génération citée |
| `indexer.py` | Script d'indexation |
| `web.py`, `templates/` | Interface |
