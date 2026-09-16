# Comment ça marche ?

```
INDEXATION (script, hors ligne)
documents Markdown
      │ découpage par section
      ├──► embeddings denses  (Ollama, qwen3-embedding:0.6b) ─┐
      └──► vecteurs BM25      (fastembed, CPU)                ├──► Qdrant
                                     + niveau d'accès du passage┘

QUESTION (en ligne)
question ─► garde d'entrée
      │
      ├──► recherche dense ──┐
      │                      ├─ fusion RRF, filtre d'accès appliqué par Qdrant
      └──► recherche BM25 ───┘
                             │
                   reranking (cross-encoder multilingue, CPU, optionnel)
                             │
                   k meilleurs passages, délimités par des balises
                             │
                          LLM ─► réponse avec citations [n]
                             │
                   citations inexistantes retirées par le code
                             │
                    garde de sortie (LLM juge) ─► réponse
```

## Points clés

- **Le filtre d'accès est dans la requête Qdrant**, pas après : un passage interdit n'est jamais
  récupéré, donc jamais envoyé au modèle ni écrit dans une trace.
- **Recherche hybride** : le dense retrouve les reformulations, le BM25 les termes exacts
  (« R5 », « article 28 »).
- **Indexation incrémentale** : l'identifiant d'un passage dérive du document et du titre de sa
  section, donc seuls les passages modifiés sont revectorisés.
- **Réponse honnête** : sans passage pertinent, le modèle répond qu'il ne trouve pas.

## Briques

| Brique | Rôle |
|---|---|
| Qdrant | Index hybride : vecteurs denses et sparses, filtre par niveau d'accès |
| Ollama, `qwen3-embedding:0.6b` | Vecteurs denses des passages et des questions |
| fastembed (ONNX, CPU) | BM25 et reranker `jina-reranker-v2-base-multilingual` |
| Ollama, `qwen3.5:9b` | Rédaction de la réponse citée |
| MLflow | Spans typés : `RETRIEVER`, `RERANKER`, garde |
