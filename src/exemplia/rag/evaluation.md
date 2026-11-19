# Évaluation

## Évaluation

`uv run python -m exemplia.llmops.evaluer rag` : rappel des documents attendus, absence de fuite
d'accès, citations présentes (ou absentes pour une question sans réponse), et `Correctness` du juge
sur les faits attendus.

Avec `qwen3-embedding:0.6b`, `qwen3.5:9b` et le reranker Jina, sur 13 questions : rappel des
documents 1,0, aucune fuite d'accès, citations 1,0, exactitude (juge) 0,92 — le point manquant est
une réponse correcte mais incomplète, qui omet un des faits attendus.
