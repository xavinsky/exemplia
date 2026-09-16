"""Configuration unique du projet, lue depuis les variables d'environnement `IACU_*` et `.env`."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

RACINE = Path(__file__).resolve().parents[3]


class Parametres(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="IACU_", env_file=RACINE / ".env", extra="ignore")

    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = "ollama"
    modele_chat: str = "qwen3.5:9b"
    modele_garde: str = "llama-guard3:8b"
    modele_embeddings: str = "qwen3-embedding:0.6b"
    modele_juge: str = "gemma4:12b"
    llm_timeout_s: float = 120.0

    # Classifieur d'injection de prompt (modèle Hugging Face), vide = règles seules. Signale sans
    # bloquer, sauf si `classifieur_injection_bloque` est activé. Nécessite le groupe `gpu`.
    classifieur_injection: str = ""
    classifieur_injection_seuil: float = 0.8
    classifieur_injection_bloque: bool = False
    # Effort de réflexion des modèles à raisonnement (`reasoning_effort`) : "none" la désactive,
    # vide laisse le comportement par défaut du modèle.
    llm_reflexion: str | None = "none"

    database_url: str = "postgresql+psycopg://iacu:iacu@localhost:5432/entreprise"
    database_url_lecture: str = "postgresql+psycopg://lecteur:lecteur@localhost:5432/entreprise"
    qdrant_url: str = "http://localhost:6333"

    # Dépôt du code, mis en lien dans le menu pour aller de la démonstration à l'implémentation.
    depot_url: str = "https://github.com/xavinsky/exemplia"

    mlflow_tracking_uri: str = "http://localhost:5000"
    tracage_actif: bool = True

    gcp_projet: str | None = None
    gcp_region: str = "europe-west1"
    modele_vertex: str = "gemini-3.8-flash"

    documents_dir: Path = RACINE / "data" / "entreprise" / "documents"
    modeles_dir: Path = RACINE / "modeles"

    @property
    def serveur_est_ollama(self) -> bool:
        return ":11434" in self.llm_base_url


@lru_cache
def parametres() -> Parametres:
    return Parametres()
