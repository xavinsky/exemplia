import pytest

from exemplia.analyse_donnees.analyste import Analyste, RequeteSQL, schema_documente
from exemplia.analyse_donnees.sql import ErreurSQL, valider_sql
from exemplia.garde.chaine import garde_standard
from exemplia.socle.llm import FauxClientLLM


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE commandes",
        "SELECT 1; DELETE FROM commandes",
        "UPDATE commandes SET statut = 'annulee'",
        "SELECT * FROM journal_actions",
        "SELECT nom, email FROM clients",
        "SELECT * FROM clients",
        "SELECT pg_sleep(10)",
        "SELECT pg_read_file('/etc/passwd')",
        "WITH x AS (DELETE FROM commandes RETURNING *) SELECT * FROM x",
        "SELECT * FROM information_schema.tables",
    ],
)
def test_sql_refuse(sql):
    with pytest.raises(ErreurSQL):
        valider_sql(sql)


def test_limit_impose():
    assert "LIMIT 200" in valider_sql("SELECT id FROM commandes")
    assert "LIMIT 10" in valider_sql("SELECT id FROM commandes LIMIT 10")
    assert "LIMIT 200" in valider_sql("SELECT id FROM commandes LIMIT 100000")


def test_requetes_legitimes():
    valider_sql(
        "WITH ca AS (SELECT date_trunc('month', date_commande) AS mois, SUM(montant) AS total "
        "FROM commandes WHERE statut <> 'annulee' GROUP BY 1) SELECT * FROM ca ORDER BY mois"
    )
    valider_sql(
        "SELECT p.libelle, SUM(l.quantite) AS quantite FROM lignes_commande l "
        "JOIN produits p ON p.id = l.produit_id GROUP BY p.libelle"
    )


def test_schema_sans_colonnes_sensibles():
    schema = schema_documente()
    assert "commandes" in schema and "email" not in schema.split("La colonne email")[0]
    assert "journal_actions" not in schema


def test_analyste_avec_correction(moteur_entreprise):
    client = FauxClientLLM(
        [
            RequeteSQL(raisonnement="", sql="SELECT * FROM journal_actions"),
            RequeteSQL(
                raisonnement="",
                sql="SELECT categorie, COUNT(*) AS nombre FROM tickets GROUP BY categorie ORDER BY categorie",
            ),
            "Il y a 60 tickets dans chaque catégorie.",
        ]
    )
    analyste = Analyste(client, moteur_entreprise, garde_standard(), dialecte="sqlite")
    resultat = analyste.repondre("Combien de tickets par catégorie ?")
    assert resultat.erreurs and "journal_actions" in resultat.erreurs[0]
    assert resultat.colonnes == ["categorie", "nombre"]
    assert [ligne[1] for ligne in resultat.lignes] == [60] * 5
    assert resultat.synthese.startswith("Il y a 60")
    assert "Corrige-la" in client.appels[1]["messages"][-1]["content"]


def test_analyste_abandonne_apres_echecs(moteur_entreprise):
    client = FauxClientLLM([RequeteSQL(raisonnement="", sql="DROP TABLE x")] * 2)
    resultat = Analyste(client, moteur_entreprise, garde_standard(), dialecte="sqlite").repondre(
        "?"
    )
    assert not resultat.colonnes and len(resultat.erreurs) == 2


def test_comptage_autorise_sur_clients():
    """`COUNT(*)` ne révèle aucune donnée, contrairement à une projection de toutes les colonnes."""
    assert valider_sql("SELECT COUNT(*) FROM clients")
    with pytest.raises(ErreurSQL):
        valider_sql("SELECT * FROM clients")


def test_dialecte_sqlalchemy_traduit_pour_sqlglot():
    """SQLAlchemy nomme le dialecte PostgreSQL « postgresql », sqlglot « postgres »."""
    from sqlalchemy import create_engine

    from exemplia.analyse_donnees.sql import dialecte_sqlglot

    postgres = create_engine("postgresql+psycopg://x:y@localhost/z").dialect.name
    assert dialecte_sqlglot(postgres) == "postgres"
    assert valider_sql("SELECT id FROM commandes", dialecte_sqlglot(postgres))
    assert dialecte_sqlglot("sqlite") == "sqlite"


def test_tables_hors_perimetre_refusees():
    """Seules les tables métier sont interrogeables : ni audit, ni sessions, ni état des workflows."""
    from exemplia.analyse_donnees.sql import TABLES_AUTORISEES

    for table in ["journal_actions", "sessions_assistant", "checkpoints", "checkpoint_writes"]:
        assert table not in TABLES_AUTORISEES
        with pytest.raises(ErreurSQL):
            valider_sql(f"SELECT * FROM {table}")
