# Comment utiliser ?

## Lancer

Page `/workflow` : charger un email d'exemple, choisir l'architecture, traiter, puis valider. Les
étapes exécutées et l'état de chaque nœud sont affichés.

| Email d'exemple | Traitement attendu |
|---|---|
| `retour-produit-casse` | retour proposé |
| `annulation` | annulation proposée |
| `menace-gros-montant` | escalade (menace juridique, montant > 300 €) |
| `retour-hors-delai` | pas d'action, délai dépassé |
| `suivi` | information, pas d'action |
| `expediteur-inconnu` | validation directe, aucun appel LLM |
| `injection` | escalade (email suspect) |

## Fichiers

| Fichier | Contenu |
|---|---|
| `commun.py` | État, contrôle, vérifications, validation humaine, envoi, compteur d'appels |
| `workflow.py` | Graphe du workflow déterministe |
| `orchestrateur.py` | Graphe superviseur et agents spécialisés |
| `emails.py` | Emails d'exemple et traitement attendu |
| `web.py`, `templates/` | Interface, checkpointer PostgreSQL |
