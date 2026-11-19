# Évaluation

## Évaluation

`uv run python -m exemplia.llmops.evaluer conformite` : part des verdicts corrects (plusieurs
verdicts acceptés quand la règle est discutable) et part des citations vérifiées.

Avec `qwen3.5:9b`, sur les trois contrats (21 verdicts) : verdicts corrects 0,90, citations
vérifiées 0,95, pour une minute de traitement. Le contrat mixte est celui qui sort le mieux, avec
ses sept verdicts corrects. Le verdict qui varie est celui de la règle R6
(responsabilité) : le contrat conforme plafonne la responsabilité à « 150 % du montant facturé au
cours des 12 derniers mois », qu'il faut rapprocher du « montant annuel du contrat » de la règle.
C'est le genre de comparaison qu'un modèle de cette taille rate une fois sur deux, et la raison pour
laquelle la décision finale reste humaine.
