import os
import tempfile

os.environ["IACU_TRACAGE_ACTIF"] = "false"
os.environ["MLFLOW_DISABLE_AGENT_HINT"] = "1"
# Stockage MLflow par défaut hors du dépôt pendant les tests.
os.environ["MLFLOW_TRACKING_URI"] = f"sqlite:///{tempfile.mkdtemp(prefix='iacu-mlflow-')}/mlflow.db"

import mlflow  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from exemplia.socle import entreprise  # noqa: E402

mlflow.tracing.disable()

DATE_REFERENCE = entreprise.date(2026, 6, 30)


@pytest.fixture
def mlflow_isole(tmp_path):
    """Serveur de suivi MLflow SQLite propre au test ; l'URI précédente est restaurée ensuite."""
    precedent = mlflow.get_tracking_uri()
    uri = f"sqlite:///{tmp_path}/mlflow.db"
    mlflow.set_tracking_uri(uri)
    mlflow.set_registry_uri(uri)
    yield tmp_path
    mlflow.flush_trace_async_logging()  # les traces du test partent vers son propre stockage
    mlflow.set_tracking_uri(precedent)
    mlflow.set_registry_uri(precedent)
    mlflow.tracing.disable()


@pytest.fixture
def moteur_entreprise():
    """Base SQLite en mémoire chargée avec les données de l'Entreprise Exemple."""
    moteur = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    entreprise.charger(moteur, entreprise.generer(DATE_REFERENCE))
    return moteur
