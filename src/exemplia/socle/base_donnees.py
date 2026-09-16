"""Schéma de l'Entreprise Exemple (SQLAlchemy Core) et accès aux bases."""

from functools import lru_cache

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    Engine,
    ForeignKey,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    create_engine,
)

from exemplia.socle.config import parametres

metadata = MetaData()

produits = Table(
    "produits",
    metadata,
    Column("id", String(8), primary_key=True),
    Column("libelle", String(80), nullable=False),
    Column("type", String(20), nullable=False, comment="produit ou abonnement"),
    Column("prix", Numeric(10, 2), nullable=False),
)

clients = Table(
    "clients",
    metadata,
    Column("id", String(8), primary_key=True),
    Column("nom", String(80), nullable=False),
    Column("email", String(120), nullable=False, unique=True),
)

commandes = Table(
    "commandes",
    metadata,
    Column("id", String(12), primary_key=True),
    Column("client_id", ForeignKey("clients.id"), nullable=False),
    Column("date_commande", Date, nullable=False),
    Column("date_livraison", Date, nullable=True),
    Column(
        "statut",
        String(20),
        nullable=False,
        comment="en_preparation, expediee, livree, annulee, retournee",
    ),
    Column("montant", Numeric(10, 2), nullable=False),
)

lignes_commande = Table(
    "lignes_commande",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("commande_id", ForeignKey("commandes.id"), nullable=False),
    Column("produit_id", ForeignKey("produits.id"), nullable=False),
    Column("quantite", Integer, nullable=False),
    Column("prix_unitaire", Numeric(10, 2), nullable=False),
)

tickets = Table(
    "tickets",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("texte", Text, nullable=False),
    Column(
        "categorie",
        String(20),
        nullable=False,
        comment="livraison, retour, facturation, compte, produit",
    ),
)

journal_actions = Table(
    "journal_actions",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("horodatage", DateTime, nullable=False),
    Column("acteur", String(40), nullable=False),
    Column("action", String(40), nullable=False),
    Column("cible", String(40), nullable=False),
    Column("cle_idempotence", String(80), nullable=False, unique=True),
    Column("details", Text, nullable=True),
)


sessions_assistant = Table(
    "sessions_assistant",
    metadata,
    Column("id", String(40), primary_key=True),
    Column("client_id", ForeignKey("clients.id"), nullable=False),
    Column("donnees", Text, nullable=False, comment="historique et action en attente, en JSON"),
    Column("mise_a_jour", DateTime, nullable=False),
)


def creer_schema(moteur_: Engine) -> None:
    metadata.create_all(moteur_)


@lru_cache
def moteur() -> Engine:
    """Accès applicatif (lecture et écriture)."""
    return create_engine(parametres().database_url, pool_pre_ping=True)


@lru_cache
def moteur_lecture() -> Engine:
    """Accès en lecture seule (rôle `lecteur`), pour exécuter du SQL généré par un LLM."""
    return create_engine(parametres().database_url_lecture, pool_pre_ping=True)
