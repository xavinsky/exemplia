# Commandes courantes d'Exemplia. « make » seul liste les cibles.
#
# Le groupe « gpu » (PyTorch, transformers) fait partie de l'installation de référence : il sert au
# fine-tuning de CamemBERT et au classifieur d'injection.
MODELES = qwen3.5:9b gemma4:12b llama-guard3:8b qwen3-embedding:0.6b

.DEFAULT_GOAL := aide
.PHONY: aide setup setup-cpu services start stop tests evaluer experiences surveillance

aide: ## Liste les commandes
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*?## ' '{printf "  make %-14s %s\n", $$1, $$2}'

setup: ## Dépendances (GPU), services, modèles, données de l'entreprise et index documentaire
	uv sync --group gpu
	@$(MAKE) --no-print-directory services

setup-cpu: ## Même installation sans GPU : ni fine-tuning CamemBERT, ni classifieur d'injection
	uv sync
	@$(MAKE) --no-print-directory services

services:
	@test -f .env || cp .env.example .env
	docker compose up -d --wait
	@if command -v ollama >/dev/null; then \
		for modele in $(MODELES); do ollama pull $$modele; done; \
	else \
		echo "Ollama introuvable : installez-le (https://ollama.com), puis relancez make setup."; \
	fi
	uv run exemplia-donnees
	uv run python -m exemplia.rag.indexer

start: ## Démarre les services et l'application sur http://127.0.0.1:8000
	docker compose up -d --wait
	uv run exemplia

stop: ## Arrête les services ; les données restent dans les volumes Docker
	docker compose stop

tests: ## Tests et lint, sans modèle ni service
	uv run pytest
	uv run ruff check src tests
	uv run ruff format --check src tests

evaluer: ## Évalue tous les exemples sur leurs jeux de test (modèles requis)
	uv run python -m exemplia.llmops.evaluer --recharger garde rag service_client conformite analyse_donnees workflow

experiences: ## Compare les approches de tri des tickets et promeut le champion
	uv run python -m exemplia.tri_tickets.experiences
	uv run python -m exemplia.tri_tickets.fine_tuning --promouvoir

surveillance: ## Note un échantillon des traces récentes de l'application
	uv run python -m exemplia.llmops.surveillance --heures 24
