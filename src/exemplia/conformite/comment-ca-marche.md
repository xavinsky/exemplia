# Comment ça marche ?

```
référentiel des achats ──► règles R1..R7
                                │
contrat ──► détection d'injection (le contrat est une donnée, pas une consigne)
                                │
        pour chaque règle, un appel séparé au LLM
                                │
              sortie structurée (Pydantic) :
              { clause citée, raisonnement, verdict }
                                │
        la citation figure-t-elle mot pour mot dans le contrat ?
              oui ─► verdict conservé
              non ─► verdict rétrogradé en « à vérifier »
                                │
                    rapport : statut global, synthèse, alertes
```

## Pourquoi une question par règle

Une seule question « ce contrat est-il conforme ? » donne un avis global invérifiable. Règle par
règle, chaque verdict est isolé, motivé par une citation, et mesurable dans l'évaluation.

Le contrat peut affirmer sa propre conformité, ou contenir une consigne adressée à une IA : il est
délimité par des balises et signalé si des formulations d'injection y sont détectées.

Au-delà de 6 000 caractères, seuls les passages qui partagent le vocabulaire de la règle sont
envoyés au modèle, et un verdict « absent » obtenu sur des extraits passe en « à vérifier » :
l'absence ne se prouve pas sur une partie du texte.

## Briques

| Brique | Rôle |
|---|---|
| Ollama, `qwen3.5:9b` | Extraction structurée, un appel par règle |
| Pydantic + `response_format` | Verdict contraint à quatre valeurs, réessai si le JSON est invalide |
| Code Python | Vérification littérale des citations, sélection des passages, statut global |
| MLflow | Un span par règle, avec le verdict et l'état de sa citation |
