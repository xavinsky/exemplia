"""Appel minimal de Gemini sur Vertex AI : génération simple et sortie structurée.

    gcloud auth application-default login
    IACU_GCP_PROJET=mon-projet uv run python -m exemplia.vertex_gemini.exemple

Service payant : aucun test automatisé n'appelle ce script.
"""

from typing import Literal

from google import genai
from google.genai import types
from pydantic import BaseModel

from exemplia.socle.config import parametres


class Categorie(BaseModel):
    categorie: Literal["livraison", "retour", "facturation", "compte", "produit"]
    justification: str


def main() -> None:
    p = parametres()
    if not p.gcp_projet:
        raise SystemExit(
            "Définir IACU_GCP_PROJET (projet Google Cloud avec l'API Vertex AI activée)."
        )

    # Authentification par Application Default Credentials : aucune clé dans le code.
    client = genai.Client(vertexai=True, project=p.gcp_projet, location=p.gcp_region)

    reponse = client.models.generate_content(
        model=p.modele_vertex,
        contents="En une phrase, qu'est-ce qu'un RAG ?",
        config=types.GenerateContentConfig(temperature=0.2, max_output_tokens=200),
    )
    print(reponse.text)

    ticket = "Bonjour, j'ai été prélevé deux fois pour ma commande CMD-0012."
    structuree = client.models.generate_content(
        model=p.modele_vertex,
        contents=f"Classe ce ticket du service client :\n{ticket}",
        config=types.GenerateContentConfig(
            system_instruction="Tu classes les demandes du service client d'Entreprise Exemple.",
            response_mime_type="application/json",
            response_schema=Categorie,
            temperature=0,
        ),
    )
    print(structuree.parsed)
    if structuree.usage_metadata:
        u = structuree.usage_metadata
        print(f"Jetons : {u.prompt_token_count} en entrée, {u.candidates_token_count} en sortie")


if __name__ == "__main__":
    main()
