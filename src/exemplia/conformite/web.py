"""Interface de l'étude de conformité."""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request

from exemplia.conformite.analyse import AnalyseurConformite, lire_referentiel
from exemplia.socle.documents import charger_documents, document
from exemplia.socle.llm import ClientLLM
from exemplia.socle.web import dep_client_llm, gabarits, mesurer

routeur = APIRouter(prefix="/conformite")
REFERENTIEL = "referentiel-achats"

# Ce que chaque contrat d'exemple donne à voir dans le rapport.
RESUMES = {
    "contrat-fournisseur-logistique": "Les sept règles respectées.",
    "contrat-fournisseur-emailing": "Les sept règles enfreintes.",
    "contrat-fournisseur-maintenance": (
        "Cas mélangés : paiement, hébergement et durée conformes ; sous-traitance RGPD absente, "
        "confidentialité limitée à la durée du contrat, responsabilité plafonnée à 2 000 euros."
    ),
}


def _contrats():
    return [d for d in charger_documents() if d.nom.startswith("contrat-")]


@routeur.get("")
def page(request: Request):
    return gabarits().TemplateResponse(
        request,
        "conformite/index.html",
        {
            "actif": "conformite",
            "contrats": _contrats(),
            "resumes": RESUMES,
            "regles": lire_referentiel(document(REFERENTIEL).contenu),
        },
    )


@routeur.post("/analyser")
def analyser(
    request: Request,
    client_llm: Annotated[ClientLLM, Depends(dep_client_llm)],
    contrat: Annotated[str, Form()] = "",
    texte: Annotated[str, Form()] = "",
):
    contenu = texte.strip() or document(contrat).contenu
    regles = lire_referentiel(document(REFERENTIEL).contenu)
    with mesurer(client_llm) as (client, mesure):
        rapport = AnalyseurConformite(client).analyser(contenu, regles)
    return gabarits().TemplateResponse(
        request, "conformite/rapport.html", {"rapport": rapport, "mesure": mesure}
    )
