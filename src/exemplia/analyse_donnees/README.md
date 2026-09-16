# Analyse de données

![Capture de la page Analyse de données](../../../captures/analyse.png)

Questions en langage naturel sur les données de l'entreprise, traduites en SQL, exécutées en
lecture seule, puis résumées.

## Besoin

Permettre à un non-spécialiste d'interroger les données (« chiffre d'affaires par mois »,
« produits les plus vendus ») sans écrire de SQL, sans risque pour la base, et avec des chiffres
exacts.

## Fonctionnement

Le déroulé, diagramme compris, est dans [Comment ça marche ?](comment-ca-marche.md) — le
texte que la page affiche.

| Protection | Ce qu'elle empêche | Où |
|---|---|---|
| Une seule instruction, arbre de type requête | `DROP`, `UPDATE`, requêtes enchaînées, CTE contenant un `DELETE` | `sql.valider_sql` |
| Liste de tables autorisées | Lecture de `journal_actions`, `information_schema`, catalogues système | `sql.valider_sql` |
| Colonnes interdites, `SELECT *` interdit sur `clients` | Lecture des emails | `sql.valider_sql` |
| Fonctions interdites (`pg_*`, `dblink`, `set_config`...) | Lecture de fichiers, attente volontaire, changement de paramètres | `sql.valider_sql` |
| `LIMIT` imposé (200) | Résultats énormes | `sql.valider_sql` |
| Rôle `lecteur` en lecture seule, `statement_timeout` de 5 s | Toute écriture, requêtes trop coûteuses, y compris si la validation a un angle mort | `docker/postgres/init.sql` |

Les deux niveaux sont nécessaires : le rôle empêche l'écriture mais pas la lecture d'une table
sensible ; la validation filtre ce qui est prévu mais peut avoir des angles morts.

**Le LLM ne calcule jamais.** Il écrit la requête puis rédige la synthèse à partir du résultat, qui
est affiché avec la requête exécutée. Le schéma envoyé au LLM est construit depuis les métadonnées
SQLAlchemy (types, clés étrangères, commentaires des colonnes) et n'inclut pas les colonnes
interdites.

## Lancer

Page `/analyse`, avec des questions d'exemple. La base est interrogée avec
`IACU_DATABASE_URL_LECTURE` (rôle `lecteur`).

## Évaluation

`uv run python -m exemplia.llmops.evaluer analyse_donnees` : chaque question du jeu a une
requête de référence ; le scorer compare les valeurs obtenues, indépendamment de l'ordre des lignes
et des colonnes et du type numérique.

## Limites

- Le LLM reçoit le schéma brut des cinq tables autorisées : une base plus large ou des
  indicateurs à définir sortent de ce que cet exemple couvre.
- La synthèse reçoit au plus 50 lignes du résultat.
- Pas de graphiques : le résultat s'affiche en table, aucun code généré n'est exécuté.

## Fichiers

| Fichier | Contenu |
|---|---|
| `sql.py` | Validation du SQL généré |
| `analyste.py` | Schéma documenté, génération, correction, exécution, synthèse |
| `web.py`, `templates/` | Interface |
