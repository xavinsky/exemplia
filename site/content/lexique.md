## Agent orchestrateur

Architecture où un LLM superviseur choisit, étape par étape, quels agents consulter, au lieu d'un enchaînement fixé par le code. Voir [Workflow d'agents](#workflow-agents).

## Appel d'outils

Le modèle répond par une demande d'appel de fonction (nom et arguments) au lieu d'un texte ; le code exécute la fonction et lui renvoie le résultat. Voir [Service client](#service-client).

## BM25

Score de recherche lexicale fondé sur la fréquence des mots d'une requête dans un passage et leur rareté dans le corpus. Il retrouve les termes exacts (« R5 », « article 28 »). Voir [RAG documentaire](#rag).

## CamemBERT

Modèle encodeur pour le français, fine-tuné ici en classifieur de tickets. Voir [Tri des tickets](#tri-tickets).

## Checkpointer

Composant LangGraph qui enregistre l'état d'un graphe à chaque étape, ce qui permet de le mettre en pause et de le reprendre plus tard ; ici dans PostgreSQL. Voir [Workflow d'agents](#workflow-agents).

## Citation vérifiée

Citation produite par le modèle et contrôlée par le code : le passage cité doit exister dans la source. Voir [Étude de conformité](#conformite).

## Cross-encoder, reranker

Modèle qui lit ensemble la question et un passage pour noter leur pertinence ; plus précis qu'une comparaison de vecteurs, il sert à réordonner les candidats d'une recherche. Voir [RAG documentaire](#rag).

## Embedding

Vecteur qui représente le sens d'un texte : deux textes proches ont des vecteurs proches. Sert à la recherche dense et à certains classifieurs. Voir [RAG documentaire](#rag).

## fastembed

Bibliothèque qui exécute des modèles d'embeddings et de reranking au format ONNX, sur le CPU. Voir [RAG documentaire](#rag).

## Garde

Ensemble des contrôles appliqués au texte qui entre dans le modèle et à la réponse qui en sort : règles, données personnelles, modération, fuite du prompt, LLM juge. Voir [Garde](#garde).

## HTMX

Bibliothèque JavaScript qui remplace des fragments de page par du HTML renvoyé par le serveur, sans framework front-end. Voir [Socle](#socle).

## Idempotence

Propriété d'une action qu'on peut rejouer sans effet supplémentaire : une annulation confirmée deux fois n'annule qu'une fois. Voir [Service client](#service-client).

## Injection de prompt

Texte qui tente de détourner les consignes du modèle. Directe, elle vient du message de l'utilisateur ; indirecte, elle est cachée dans un document, un email ou un résultat d'outil. Voir [Garde](#garde).

## LangGraph

Bibliothèque qui décrit un traitement par LLM comme un graphe d'étapes à état partagé, avec pause pour validation humaine. Voir [Workflow d'agents](#workflow-agents).

## Llama Guard 3

Modèle de modération qui classe un texte comme sûr ou dangereux, avec la catégorie de risque. Servi par Ollama. Voir [Garde](#garde).

## LLM juge

Modèle qui évalue la réponse d'un autre selon des critères écrits : en ligne comme filtre de sortie, ou hors ligne pour l'évaluation. Volontairement différent du modèle qui répond. Voir [LLMOps](#llmops).

## LLMOps

Pratiques d'exploitation d'une application à base de LLM : traces, jeux d'évaluation, scorers, surveillance des réponses en production. Voir [LLMOps](#llmops).

## MLflow

Plateforme de suivi : traces des appels, runs d'expériences et d'évaluation, registry des modèles. Voir [LLMOps](#llmops).

## Ollama

Serveur de modèles local qui expose une API compatible OpenAI ; il sert ici tous les modèles de conversation, de juge, de modération et d'embeddings. Voir [Installation et exécution](#installation).

## Presidio

Bibliothèque de détection et de masquage des données personnelles (noms, adresses, IBAN, cartes bancaires), utilisée avec un modèle spaCy français. Voir [Garde](#garde).

## Qdrant

Base vectorielle qui stocke les vecteurs denses et BM25 des passages et applique les filtres d'accès dans la requête. Voir [RAG documentaire](#rag).

## RAG

Retrieval-Augmented Generation : on récupère d'abord les passages pertinents d'une base documentaire, puis le modèle répond à partir d'eux seuls, en les citant. Voir [RAG documentaire](#rag).

## Registry, alias champion

Registre des versions de modèles de MLflow ; l'alias `champion` désigne la version servie, et se déplace quand une meilleure version est promue. Voir [Tri des tickets](#tri-tickets).

## RRF

Reciprocal Rank Fusion : fusion de plusieurs classements (dense, BM25) qui somme l'inverse des rangs de chaque passage. Voir [RAG documentaire](#rag).

## Scorer

Fonction qui note une réponse sur un critère (rappel, citation, exactitude...) lors d'une évaluation MLflow. Voir [LLMOps](#llmops).

## sqlglot

Analyseur SQL utilisé pour vérifier qu'une requête générée est un `SELECT` unique sur les tables autorisées avant de l'exécuter. Voir [Analyse de données](#analyse-donnees).

## Sortie structurée

Réponse du modèle contrainte par un schéma (ici Pydantic) et validée par le code, au lieu d'un texte libre. Voir [Étude de conformité](#conformite).

## Trace, span

Enregistrement d'une requête et de ses étapes (appel au modèle, recherche, outil, contrôle de garde), avec entrées, sorties et durées. Voir [LLMOps](#llmops).

## Vertex AI

Plateforme d'IA de Google Cloud, qui sert ici le modèle Gemini dans le seul exemple cloud. Voir [Vertex AI + Gemini](#vertex-gemini).
