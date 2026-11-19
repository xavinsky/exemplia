# Comment utiliser ?

## Lancer

Page `/service-client` de l'application. Choisir le client dans le menu latéral. Exemples de
demandes cohérentes avec les données :

| Client | Demande | Résultat attendu |
|---|---|---|
| Client 17 | « Annulez ma commande CMD-0053 » | action proposée, confirmation |
| Client 03 | « Le Produit C de CMD-0034 est cassé, je veux le renvoyer » | retour proposé |
| Client 01 | « Je veux retourner CMD-0024 » | refus : délai dépassé |
| Client 09 | « Je vais porter plainte » | transfert à un conseiller |

Les demandes ci-dessus supposent les données dans leur état initial : confirmer une annulation
change le statut de la commande. Recharger avec `uv run exemplia-donnees`.

## Fichiers

| Fichier | Contenu |
|---|---|
| `outils.py` | Schémas des outils, lecture, éligibilité, exécution idempotente, journal, détection des menaces de recours |
| `assistant.py` | Boucle d'outils, garde, action en attente, confirmation |
| `sessions.py` | Enregistrement des sessions en base |
| `web.py`, `templates/` | Interface |
