# LLMOps

Observabilité, évaluation et surveillance des exemples avec MLflow 3.

## Besoin

Un assistant LLM change de comportement dès qu'on modifie un prompt, un modèle ou un paramètre. Sans
mesure, on ne sait pas si une modification améliore ou dégrade. Il faut :

- **voir** ce qui s'est passé pour une requête (traces) ;
- **mesurer** la qualité sur un jeu de test fixe, avant chaque mise en production (évaluation) ;
- **suivre** la qualité réelle en production (surveillance).

## Limites

- Avec vLLM au lieu d'Ollama, `uri_juge()` produit `openai:/<modèle>` : il faut alors pointer le
  fournisseur OpenAI de MLflow vers le serveur vLLM, ou construire les juges avec
  `mlflow.genai.make_judge(..., base_url=...)`.
- Les jeux comptent quelques dizaines de cas : ils détectent les régressions nettes, pas les écarts
  de quelques points. On les enrichit avec les cas réels mal traités repérés en surveillance.
- Le juge renvoie parfois un contenu vide, sur lequel MLflow échoue (`Failed to parse response from
  judge model`) : le scorer est alors en erreur pour ce cas, sans que l'évaluation s'arrête. Le même
  appel rejoué aboutit ; c'est une instabilité du serveur de modèles, pas un problème de prompt.
- Deux exécutions identiques ne donnent pas exactement les mêmes scores : le serveur de modèles
  n'est pas déterministe d'un lot à l'autre, et le juge lui-même varie. Comparer des écarts d'un
  point n'a pas de sens ; répéter l'évaluation avant de conclure sur un changement fin.

La suite : [Comment ça marche ?](fonctionnement.md) · [Comment utiliser ?](utilisation.md) · [Évaluation](evaluation.md).
