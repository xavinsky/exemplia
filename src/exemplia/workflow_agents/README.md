# Workflow d'agents

![Capture de la page Workflow d'agents](../../../captures/workflow.png)

Traitement de bout en bout d'un email entrant au service client, jusqu'à un brouillon de réponse
validé par un conseiller, avec deux architectures comparables.

## Deux architectures

| | Workflow déterministe | Agent orchestrateur |
|---|---|---|
| Qui décide des étapes | Le code | Un LLM superviseur |
| Appels LLM | 3 par email (aucun si l'expéditeur est inconnu ou l'email suspect) | Variable (superviseur + agents consultés) |
| Prévisibilité, test | Élevées : chaque étape se teste seule | Plus faibles : dépend des choix du superviseur |
| Adaptation aux cas imprévus | Faible : il faut ajouter une branche | Élevée |
| Usage | La majorité des traitements en production | Demandes dont on ne peut pas figer le déroulé |

Dans les deux cas, le graphe **se met en pause avant tout envoi** (`interrupt` de LangGraph), et
l'action demandée (annulation, retour) n'est exécutée qu'avec l'accord explicite du conseiller.

## Workflow déterministe

Le déroulé, diagramme compris, est dans [Comment ça marche ?](comment-ca-marche.md) — le
texte que la page affiche.

| Nœud | Rôle |
|---|---|
| `controler` | Identifie le client par l'adresse d'expédition, détecte les formulations d'injection et les menaces de recours (code). Un email d'expéditeur inconnu ou suspect va directement au conseiller avec une réponse d'attente écrite par le code |
| `classer` | Catégorie et urgence (sortie structurée) |
| `extraire` | Référence de commande, type de demande, résumé, menace juridique |
| `verifier` | Faits vérifiés par le code : commande du client, éligibilité, règles d'escalade du guide interne (menace juridique, montant > 300 €) |
| `rediger` | Brouillon à partir des faits vérifiés et des politiques |
| `validation_humaine` | Pause : le conseiller corrige, approuve ou rejette, et choisit d'exécuter ou non l'action |
| `envoyer` | Exécute l'action si demandée (idempotente), journalise la réponse |

## Agent orchestrateur

Le superviseur choisit les agents à consulter. Les garde-fous restent dans le code :

- nombre d'étapes borné (`max_etapes`) ;
- sous-agent commandes limité aux données du client identifié ;
- action retenue seulement si le code confirme son éligibilité, avec la même règle d'escalade au-delà
  de 300 € que le workflow ;
- l'agent de rédaction reçoit les réponses des autres agents et les motifs d'escalade : sans elles,
  il invente l'issue de la demande (« votre commande a bien été annulée ») ;
- `completer_brouillon` fait rédiger un brouillon si le superviseur s'est arrêté sans le demander.

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

## Évaluation

`uv run python -m exemplia.llmops.evaluer workflow` exécute chaque email avec les deux
architectures jusqu'à la validation humaine : action proposée, escalade, nombre d'appels LLM et juge
sur le brouillon.

Avec `qwen3.5:9b`, sur les 7 emails d'exemple :

| | Workflow déterministe | Agent orchestrateur |
|---|---|---|
| Action correcte | 1,00 | 1,00 |
| Escalade correcte | 1,00 | 1,00 |
| Consignes du brouillon (juge) | 1,00 | 1,00 |
| Appels LLM par email | 2,1 | 5,0 |

Même résultat métier, pour 2,4 fois plus d'appels au modèle côté orchestrateur : c'est le compromis
coût contre souplesse. Sur ces demandes, dont le déroulé est connu, le workflow déterministe est le
bon choix ; l'orchestrateur garde l'avantage sur des demandes qu'on ne peut pas figer.

## Limites

- L'application web enregistre l'état des traitements en pause dans PostgreSQL
  (`PostgresSaver`, tables `checkpoint*`) : une validation peut avoir lieu après un redémarrage ou
  sur un autre processus. Les tests et l'évaluation utilisent le checkpointer en mémoire.
- L'identification du client par l'adresse email ne suffit pas à authentifier l'expéditeur (adresse
  usurpable) : d'où la validation humaine avant toute action.

## Fichiers

| Fichier | Contenu |
|---|---|
| `commun.py` | État, contrôle, vérifications, validation humaine, envoi, compteur d'appels |
| `workflow.py` | Graphe du workflow déterministe |
| `orchestrateur.py` | Graphe superviseur et agents spécialisés |
| `emails.py` | Emails d'exemple et traitement attendu |
| `web.py`, `templates/` | Interface, checkpointer PostgreSQL |
