# Garde

![Capture de la page Garde](../../../captures/garde.png)

Filtres appliqués avant l'envoi au LLM (entrée) et avant l'envoi à l'utilisateur (sortie). Utilisés
par tous les exemples, testables seuls sur la page `/garde`.

## Besoin

Dès qu'un texte libre atteint un LLM, il faut se protéger contre :

- l'**injection de prompt** directe (« ignore tes instructions ») et **indirecte**, cachée dans un
  document, un email ou un résultat d'outil ;
- l'envoi de **données personnelles** au modèle ou dans les traces ;
- les **contenus dangereux** en entrée comme en sortie ;
- les **réponses non fiables** : hors périmètre, non sourcées, promesses que l'entreprise ne tient
  pas, reprise du prompt système.

## Limites

- Les règles d'injection arrêtent les formulations courantes, pas les attaques reformulées (fausse
  politique, fausse note interne) ; Llama Guard ne les classe pas non plus comme dangereuses. Avec
  le classifieur en signalement, ces messages passent au modèle mais l'alerte est visible.
- La détection des noms de personnes repose sur spaCy `fr_core_news_md`. Ce modèle, comme le petit
  `fr_core_news_sm`, étiquette parfois un mot en tête de phrase comme une personne (« Livraison en
  retard », « Remboursez-moi ») : les détections qui ne contiennent aucun nom propre sont écartées.
  L'adresse `exemple.test` n'est pas reconnue comme email (domaine de premier niveau réservé).
- Le juge double la latence de la réponse. Sur 12 Go de VRAM, le juge et le modèle principal
  alternent en mémoire, ce qui ajoute le temps de chargement.

La suite : [Comment ça marche ?](comment-ca-marche.md) · [Comment utiliser ?](utilisation.md) · [Évaluation](evaluation.md).
