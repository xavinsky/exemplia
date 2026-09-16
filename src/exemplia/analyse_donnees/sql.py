"""Validation du SQL généré par le LLM, avant toute exécution.

Défense en profondeur : cette validation (une seule requête SELECT, tables et colonnes autorisées,
LIMIT imposé) s'ajoute au rôle PostgreSQL en lecture seule avec délai maximal. Aucune des deux
protections ne suffit seule : le rôle empêche d'écrire mais pas de lire une table sensible ou de
lancer une requête très coûteuse ; la validation filtre ce qui est prévu mais peut avoir des angles
morts.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp

TABLES_AUTORISEES = {"produits", "clients", "commandes", "lignes_commande", "tickets"}
COLONNES_INTERDITES = {"email"}
FONCTIONS_INTERDITES_PREFIXES = ("pg_", "lo_", "dblink", "set_config", "current_setting", "sleep")
LIMITE_LIGNES = 200


# SQLAlchemy et sqlglot ne nomment pas les dialectes de la même façon.
DIALECTES = {"postgresql": "postgres"}


def dialecte_sqlglot(nom: str) -> str:
    return DIALECTES.get(nom, nom)


class ErreurSQL(ValueError):
    pass


def valider_sql(
    sql: str,
    dialecte: str = "postgres",
    tables_autorisees: set[str] = TABLES_AUTORISEES,
    colonnes_interdites: set[str] = COLONNES_INTERDITES,
    limite: int = LIMITE_LIGNES,
) -> str:
    try:
        instructions = [i for i in sqlglot.parse(sql, read=dialecte) if i is not None]
    except sqlglot.errors.ParseError as erreur:
        raise ErreurSQL(f"SQL invalide : {erreur}") from erreur
    if len(instructions) != 1:
        raise ErreurSQL("Une seule requête est autorisée.")
    arbre = instructions[0]

    if not isinstance(arbre, exp.Query):
        raise ErreurSQL("Seules les requêtes SELECT sont autorisées.")
    interdits = (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter, exp.Command)
    if any(arbre.find_all(*interdits)):
        raise ErreurSQL("La requête contient une instruction de modification.")

    cte = {c.alias_or_name.lower() for c in arbre.find_all(exp.CTE)}
    tables = {t.name.lower() for t in arbre.find_all(exp.Table)} - cte
    if hors_liste := tables - tables_autorisees:
        raise ErreurSQL(f"Tables non autorisées : {', '.join(sorted(hors_liste))}.")

    colonnes = {c.name.lower() for c in arbre.find_all(exp.Column)}
    if interdites := colonnes & colonnes_interdites:
        raise ErreurSQL(f"Colonnes non autorisées : {', '.join(sorted(interdites))}.")
    # `COUNT(*)` ne renvoie aucune donnée de la table : seule la projection de toutes les colonnes
    # est interdite dès que `clients` est interrogée.
    projections = [e for e in arbre.find_all(exp.Star) if not isinstance(e.parent, exp.Count)]
    if projections and "clients" in tables:
        raise ErreurSQL("SELECT * interdit sur la table clients : listez les colonnes.")

    for fonction in arbre.find_all(exp.Func):
        nom = (
            fonction.sql_name() if not isinstance(fonction, exp.Anonymous) else fonction.name
        ).lower()
        if nom.startswith(FONCTIONS_INTERDITES_PREFIXES):
            raise ErreurSQL(f"Fonction non autorisée : {nom}.")

    limite_actuelle = arbre.args.get("limit")
    valeur = None
    if limite_actuelle is not None:
        expression = limite_actuelle.expression
        valeur = int(expression.name) if isinstance(expression, exp.Literal) else None
    if valeur is None or valeur > limite:
        arbre = arbre.limit(limite)
    return arbre.sql(dialect=dialecte)
