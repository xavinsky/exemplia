# Comment ça marche ?

```
question en langage naturel
      │
      ▼
 garde d'entrée
      │
      ▼
 LLM + schéma documenté (tables, types, clés étrangères, commentaires)
      │ { raisonnement, sql }
      ▼
 validation sqlglot ─── refus ──┐
  · une seule instruction SELECT │
  · tables autorisées seulement  │ l'erreur est renvoyée au modèle,
  · colonnes interdites          │ qui corrige (une tentative)
  · fonctions interdites         │
  · LIMIT imposé                 │
      │                          │
      ▼                          │
 exécution avec le rôle PostgreSQL « lecteur » ─── erreur ──┘
 (lecture seule, délai maximal de 5 s)
      │
      ▼
 résultat ─► LLM ─► synthèse, affichée à côté de la requête exécutée
```

## Deux protections indépendantes

La validation filtre ce qui est prévu, mais peut avoir des angles morts. Le rôle `lecteur` interdit
toute écriture, quoi qu'il arrive, mais n'empêche pas de lire une table sensible. Il faut les deux.

**Le modèle ne calcule jamais** : il écrit la requête, PostgreSQL produit les chiffres, et le modèle
rédige la synthèse à partir du résultat, affiché à côté pour être vérifiable.

## Briques

| Brique | Rôle |
|---|---|
| sqlglot | Analyse syntaxique du SQL généré et application des règles |
| PostgreSQL, rôle `lecteur` | Exécution en lecture seule, `statement_timeout` de 5 s |
| SQLAlchemy | Schéma documenté envoyé au modèle, construit depuis les métadonnées |
| Ollama, `qwen3.5:9b` | Génération de la requête et rédaction de la synthèse |
