"""Application web qui regroupe tous les exemples : `uv run exemplia`."""

import importlib
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from exemplia.socle import tracage
from exemplia.socle.config import parametres
from exemplia.socle.web import gabarits

MODULES_WEB = [
    "service_client",
    "rag",
    "conformite",
    "analyse_donnees",
    "tri_tickets",
    "workflow_agents",
    "garde",
]


def creer_app() -> FastAPI:
    tracage.reponses_rapides()
    tracage.activer("exemplia")
    app = FastAPI(title="IA cas d'usage")
    app.mount(
        "/static",
        StaticFiles(directory=Path(__file__).parent / "socle" / "static"),
        name="static",
    )
    for nom in MODULES_WEB:
        try:
            module = importlib.import_module(f"exemplia.{nom}.web")
        except ModuleNotFoundError as erreur:
            if erreur.name != f"exemplia.{nom}.web" and erreur.name != f"exemplia.{nom}":
                raise
            continue
        app.include_router(module.routeur)

    @app.get("/")
    def accueil(request: Request):
        p = parametres()
        return gabarits().TemplateResponse(
            request,
            "socle/accueil.html",
            {
                "actif": "",
                "modele_chat": p.modele_chat,
                "modele_juge": p.modele_juge,
                "mlflow_url": p.mlflow_tracking_uri,
            },
        )

    return app


def main() -> None:
    uvicorn.run("exemplia.app:creer_app", factory=True, host="127.0.0.1", port=8000)
