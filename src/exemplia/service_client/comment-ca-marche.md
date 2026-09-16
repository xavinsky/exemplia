# Comment ça marche ?

```
message du client
      │
      ▼
 garde d'entrée ──── bloque ──► message de refus
 (longueur, injection, données personnelles, Llama Guard)
      │
      ▼
   LLM (qwen3.5:9b) ◄──────────────────────┐
      │  décide d'appeler un outil          │
      ├─ lecture ─► PostgreSQL ─────────────┤ résultat délimité
      ├─ écriture ─► éligibilité vérifiée par le code
      │             action mise en attente  │
      └─ transfert ─► journal d'audit ──────┘
      │ (texte final)
      ▼
 garde de sortie ──── bloque ──► transfert à un conseiller
 (fuite du prompt, données sensibles, LLM juge gemma4:12b)
      │
      ▼
 réponse + bouton « Confirmer » si une action est en attente
```

## Ce que fait le code, jamais le modèle

- **L'identité du client** vient de la session ; le modèle ne choisit jamais l'identifiant, donc un
  outil ne peut pas lire les commandes de quelqu'un d'autre.
- **L'éligibilité** d'une annulation (statut `en_preparation`) ou d'un retour (livrée depuis 30 jours
  au plus, au moins un produit physique) est vérifiée en Python.
- **L'exécution** n'a lieu qu'après le clic du client, avec une clé d'idempotence en base.
- **L'escalade** sur menace de recours (plainte, avocat, association de consommateurs) est détectée
  par une expression régulière, avant même d'appeler le modèle.

## Briques

| Brique | Rôle |
|---|---|
| Ollama, `qwen3.5:9b` | Conversation et appels d'outils, API compatible OpenAI |
| Ollama, `gemma4:12b` | LLM juge de la garde de sortie |
| Ollama, `llama-guard3:8b` | Modération du message entrant |
| Presidio + spaCy `fr_core_news_md` | Masquage des données personnelles |
| PostgreSQL | Commandes, journal d'audit, sessions de conversation |
| MLflow | Traces : appels au modèle, outils, verdicts de garde |
| FastAPI + HTMX | Interface et rafraîchissement du fil sans JavaScript applicatif |
