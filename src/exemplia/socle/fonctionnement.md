# Fonctionnement

## Client LLM

Le code des exemples ne dépend que du protocole `ClientLLM`. Deux implémentations :

- `ClientOpenAICompatible` : tout serveur exposant l'API OpenAI (Ollama, vLLM, passerelle). La
  réflexion des modèles à raisonnement est désactivée par défaut (`IACU_LLM_REFLEXION=none`, passé
  en `reasoning_effort`) : avec `qwen3.5:9b`, elle ajoute plusieurs centaines de jetons et une
  vingtaine de secondes par appel. Ollama renvoie la réflexion dans un champ séparé ; les balises
  `<think>` laissées dans le contenu par d'autres serveurs sont retirées du texte. `extraire`
  impose un schéma JSON (`response_format`) et renvoie une instance Pydantic validée, avec une
  nouvelle tentative qui renvoie l'erreur de validation au modèle.
- `FauxClientLLM` : renvoie un scénario de réponses prévues (texte, appels d'outils, objets
  Pydantic, ou fonction). Il enregistre les messages reçus, ce qui permet de vérifier dans les
  tests ce qui est envoyé au modèle. Ses embeddings sont déterministes (mots hachés).

Les messages suivent le format Chat Completions : `ReponseLLM.message()` et `message_outil()`
produisent les messages à réinjecter dans l'historique.

## Données de l'Entreprise Exemple

| Table | Contenu |
|---|---|
| `produits` | 8 produits génériques et 2 abonnements |
| `clients` | 20 clients (`Client 01`, `client01@exemple.test`) |
| `commandes`, `lignes_commande` | 60 commandes sur les 90 derniers jours |
| `tickets` | 300 demandes étiquetées, 60 par catégorie |
| `journal_actions` | Audit des actions, avec clé d'idempotence unique |
| `sessions_assistant` | Conversations du service client en cours |

La génération utilise une graine fixe. Les dates sont calculées par rapport au jour du chargement
(ou `--reference AAAA-MM-JJ`) : les écarts restent identiques, donc les règles métier donnent les
mêmes résultats quel que soit le jour. Les tickets sont produits à partir de 14 formulations
par catégorie, avec du bruit (minuscules, accents absents, fautes de frappe) ; chaque ticket garde
en mémoire sa formulation d'origine (`modele`, hors base) pour séparer entraînement et test.

Documents (`data/entreprise/documents/`), avec un en-tête `titre` / `acces` :

| Document | Accès |
|---|---|
| Conditions générales de vente, politique de retour, FAQ, politique de données personnelles | public |
| Guide interne du service client, référentiel des achats | interne |
| Contrat logistique (conforme), contrat d'emailing (tous les écarts), contrat de maintenance (cas mélangés) | confidentiel |

## Web

Le menu renvoie au dépôt du code (`IACU_DEPOT_URL`, vide pour retirer le lien) : depuis une
démonstration, on va voir l'implémentation en un clic.

Toutes les pages d'exemple partagent la même grille (`.travail` dans la feuille de style) :
l'interface à gauche avec sa réponse en dessous, les informations utiles au milieu (commandes du
client, référentiel, tables interrogeables, chaîne de contrôles), les boutons « Essayer » à droite.
Deux colonnes quand il n'y a rien à montrer au milieu, une seule sous 1 100 pixels de large.

Chaque exemple explique son fonctionnement dans `<exemple>/comment-ca-marche.md` : diagramme,
points clés et tableau des briques utilisées. Le fichier se lit dans le dépôt, et
`explications.html()` le rend dans la section repliable « Comment ça marche ? », présente sur toutes
les pages via le gabarit de base. Ajouter un exemple, c'est donc ajouter ce fichier, sans toucher
aux gabarits.

`web.mesurer(client_llm)` enveloppe le client dans un `ClientJournal` : il compte les appels,
chronomètre la requête et retient chaque échange avec le modèle. Le gabarit `socle/trace.html`
affiche le tout sous chaque réponse — une ligne repliée « Trace · N appels au modèle · X s » qui
s'ouvre sur les messages envoyés et les réponses reçues, appel par appel. Le client journalisé est
passé aux composants *et* à la garde : la modération et le juge y figurent aussi.

C'est l'outil de diagnostic le plus direct du projet : il montre le prompt système réellement
envoyé, les outils proposés au modèle, ce que le juge a reçu comme sources et ce qu'il a répondu.

`web.gabarits()` charge les gabarits du socle et de chaque exemple
(`<module>/templates/<module>/*.html`). Les routes reçoivent la base et le client LLM par
dépendances FastAPI (`dep_moteur`, `dep_client_llm`), remplacées dans les tests par
`app.dependency_overrides`.

## Traces

`tracage.activer(experience)` active l'autolog OpenAI (appels au serveur de modèles) et LangChain
(graphes LangGraph). `tracage.decrire_trace(tags=..., metadata=...)` pose le tag `exemple`,
l'utilisateur et la session sur la trace en cours, et ne fait rien quand il n'y en a pas (tests,
contrôle de la fonction de prédiction par MLflow). Si le serveur MLflow est injoignable, l'application continue sans traces.
`tracage.reponses_rapides()` supprime les nouvelles tentatives HTTP de MLflow dans l'application
web, pour qu'une page ne reste pas bloquée quand MLflow est arrêté.
