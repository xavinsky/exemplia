"""Exemples de référence des cas d'usage d'IA en entreprise."""

import os

# Avant tout import de MLflow : son message d'accroche s'adresse aux assistants de code et n'a rien
# à faire dans la sortie des scripts et de l'application.
os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
