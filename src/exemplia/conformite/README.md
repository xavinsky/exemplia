# Étude de conformité

![Capture de la page Étude de conformité](../../../captures/conformite.png)

Vérification d'un contrat fournisseur contre le référentiel interne des achats, règle par règle,
avec citation contrôlée et décision finale humaine.

## Besoin

Relire des contrats contre une liste de clauses obligatoires (délais de paiement, RGPD,
localisation des données, résiliation...) est long et répétitif. Le LLM prépare l'analyse ; le
juriste vérifie les points signalés au lieu de tout relire.

## Limites

- La sélection des passages d'un contrat long est lexicale (mots communs avec la règle, sans
  modèle) : une clause rédigée avec un vocabulaire éloigné de la règle peut être manquée.
- Sept appels au LLM par contrat, exécutés l'un après l'autre.
- La règle R6 demande de comparer un plafond exprimé en pourcentage d'un montant facturé au montant
  annuel du contrat : le jeu d'évaluation accepte plusieurs verdicts, et c'est la règle la moins
  stable d'une exécution à l'autre.

La suite : [Comment ça marche ?](comment-ca-marche.md) · [Comment utiliser ?](utilisation.md) · [Évaluation](evaluation.md).
