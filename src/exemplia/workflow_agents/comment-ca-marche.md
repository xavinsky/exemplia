# Comment ça marche ?

```
WORKFLOW DÉTERMINISTE (le code fixe les étapes, 3 appels LLM)

controler ──(expéditeur inconnu ou email suspect)──────────────┐
  (code)                                                        ▼
 classer ─► extraire ─► verifier ─► rediger ─► validation_humaine ─► envoyer
  (LLM)      (LLM)      (code)      (LLM)         (pause)         └► cloturer

AGENT ORCHESTRATEUR (le superviseur choisit, 5 appels LLM en moyenne)

controler ─► superviseur ⇄ agents ─► completer_brouillon ─► validation_humaine ─► …
               (LLM)         │
        agent_commandes (LLM + outils de lecture)
        agent_documentation (LLM + politiques)
        agent_redaction (LLM, à partir des faits recueillis)
        proposer_action (éligibilité vérifiée par le code)
        signaler_escalade
```

## La pause avant l'envoi

Les deux graphes s'arrêtent avant tout envoi (`interrupt` de LangGraph) : le conseiller relit,
corrige, approuve ou rejette, et décide d'exécuter ou non l'action. L'état du traitement en pause
est enregistré dans PostgreSQL, donc il survit à un redémarrage de l'application.

Les garde-fous restent dans le code, quelle que soit l'architecture : identification du client par
l'adresse d'expédition, éligibilité revérifiée, nombre d'étapes borné, escalade automatique sur
menace de recours ou remboursement supérieur à 300 euros.

À justesse égale sur les emails d'exemple, l'orchestrateur consomme deux fois et demie plus d'appels
au modèle : la souplesse se paie.

## Briques

| Brique | Rôle |
|---|---|
| LangGraph | Graphes d'état, pause `interrupt`, reprise après validation |
| `PostgresSaver` | Checkpointer persistant des traitements en pause |
| Ollama, `qwen3.5:9b` | Classification, extraction, rédaction, supervision |
| PostgreSQL | Commandes, éligibilité, journal d'audit |
| MLflow | Autolog LangChain : un span par nœud du graphe |
