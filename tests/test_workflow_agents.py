from fastapi.testclient import TestClient
from langgraph.types import Command
from sqlalchemy import select

from exemplia.socle import base_donnees as bd
from exemplia.socle.llm import AppelOutil, ClientJournal, FauxClientLLM, ReponseLLM
from exemplia.workflow_agents.emails import EMAILS
from exemplia.workflow_agents.orchestrateur import construire_orchestrateur
from exemplia.workflow_agents.workflow import Classification, Extraction, construire_workflow
from tests.conftest import DATE_REFERENCE

EMAIL = {e["id"]: e for e in EMAILS}


def _entree(email):
    return {k: email[k] for k in ("expediteur", "objet", "corps")}


def _statut(moteur, commande_id):
    with moteur.connect() as cx:
        return cx.scalar(select(bd.commandes.c.statut).where(bd.commandes.c.id == commande_id))


def test_emails_coherents_avec_les_donnees(moteur_entreprise):
    assert _statut(moteur_entreprise, "CMD-0053") == "en_preparation"
    assert _statut(moteur_entreprise, "CMD-0034") == "livree"
    assert _statut(moteur_entreprise, "CMD-0021") == "expediee"


def test_workflow_annulation_apres_validation(moteur_entreprise):
    client = ClientJournal(
        FauxClientLLM(
            [
                Classification(categorie="retour", urgence="normale"),
                Extraction(
                    commande_id="CMD-0053",
                    demande="annulation",
                    resume="annuler",
                    menace_juridique=False,
                ),
                "Bonjour, nous pouvons annuler votre commande.",
            ]
        )
    )
    graphe = construire_workflow(client, moteur_entreprise, DATE_REFERENCE)
    config = {"configurable": {"thread_id": "t1"}}
    resultat = graphe.invoke(_entree(EMAIL["annulation"]), config)

    assert "__interrupt__" in resultat
    assert resultat["action_proposee"] == {"type": "annulation", "commande_id": "CMD-0053"}
    assert client.appels == 3
    assert _statut(moteur_entreprise, "CMD-0053") == "en_preparation"

    final = graphe.invoke(
        Command(resume={"approuver": True, "texte": "Annulée.", "executer_action": True}), config
    )
    assert final["statut"] == "envoyee"
    assert _statut(moteur_entreprise, "CMD-0053") == "annulee"


def test_workflow_escalade_montant_et_menace(moteur_entreprise):
    client = FauxClientLLM(
        [
            Classification(categorie="retour", urgence="haute"),
            Extraction(
                commande_id="CMD-0003",
                demande="reclamation",
                resume="remboursement",
                menace_juridique=True,
            ),
            "Un responsable reprend votre dossier.",
        ]
    )
    graphe = construire_workflow(client, moteur_entreprise, DATE_REFERENCE)
    resultat = graphe.invoke(
        _entree(EMAIL["menace-gros-montant"]), {"configurable": {"thread_id": "t2"}}
    )
    motifs = " ".join(resultat["motifs_escalade"])
    assert "juridique" in motifs and "300" in motifs


def test_workflow_expediteur_inconnu_sans_llm(moteur_entreprise):
    client = FauxClientLLM()
    graphe = construire_workflow(client, moteur_entreprise, DATE_REFERENCE)
    resultat = graphe.invoke(
        _entree(EMAIL["expediteur-inconnu"]), {"configurable": {"thread_id": "t3"}}
    )
    assert "__interrupt__" in resultat and not client.appels


def test_workflow_rejet(moteur_entreprise):
    client = FauxClientLLM(
        [
            Classification(categorie="retour", urgence="normale"),
            Extraction(
                commande_id="CMD-0053", demande="annulation", resume="", menace_juridique=False
            ),
            "Brouillon",
        ]
    )
    graphe = construire_workflow(client, moteur_entreprise, DATE_REFERENCE)
    config = {"configurable": {"thread_id": "t4"}}
    graphe.invoke(_entree(EMAIL["annulation"]), config)
    final = graphe.invoke(Command(resume={"approuver": False, "executer_action": True}), config)
    assert final["statut"] == "rejetee"
    assert _statut(moteur_entreprise, "CMD-0053") == "en_preparation"


def _appel(nom, **arguments):
    return ReponseLLM(appels_outils=[AppelOutil(id=f"id-{nom}", nom=nom, arguments=arguments)])


def test_orchestrateur_delegue_puis_valide(moteur_entreprise):
    client = FauxClientLLM(
        [
            _appel("agent_commandes", question="Statut de CMD-0034 et retour possible ?"),
            _appel("verifier_eligibilite", type="retour", commande_id="CMD-0034"),
            "Livrée récemment, retour possible.",
            _appel("proposer_action", type="retour", commande_id="CMD-0034"),
            _appel("agent_redaction", consignes="Accepter le retour"),
            "Bonjour, votre retour est accepté sous réserve de validation.",
            "Brouillon rédigé.",
        ]
    )
    graphe = construire_orchestrateur(client, moteur_entreprise, DATE_REFERENCE)
    resultat = graphe.invoke(
        _entree(EMAIL["retour-produit-casse"]), {"configurable": {"thread_id": "o1"}}
    )
    assert "__interrupt__" in resultat
    assert resultat["action_proposee"] == {"type": "retour", "commande_id": "CMD-0034"}
    assert resultat["brouillon"].startswith("Bonjour")
    # 2e appel du sous-agent commandes : il reçoit le résultat délimité de son outil.
    outil = client.appels[2]["messages"][-1]
    assert outil["role"] == "tool" and outil["content"].startswith("<resultat_outil>")


def test_orchestrateur_ne_peut_pas_forcer_une_action(moteur_entreprise):
    client = FauxClientLLM(
        [
            _appel("proposer_action", type="annulation", commande_id="CMD-0024"),
            "Terminé.",
            "Bonjour, le délai de retour est dépassé.",
        ]
    )
    graphe = construire_orchestrateur(client, moteur_entreprise, DATE_REFERENCE)
    resultat = graphe.invoke(
        _entree(EMAIL["retour-hors-delai"]), {"configurable": {"thread_id": "o2"}}
    )
    assert not resultat.get("action_proposee")
    # Le superviseur s'est arrêté sans agent de rédaction : le brouillon est complété par le code.
    assert resultat["brouillon"] == "Bonjour, le délai de retour est dépassé."
    assert "faits_recueillis" in client.appels[-1]["messages"][-1]["content"]


def test_orchestrateur_escalade_montant_verifiee_par_le_code(moteur_entreprise):
    client = FauxClientLLM(
        [
            _appel("proposer_action", type="retour", commande_id="CMD-0003"),
            _appel("agent_redaction", consignes="Réponse d'attente"),
            "Un responsable reprend votre dossier.",
            "Brouillon rédigé.",
        ]
    )
    graphe = construire_orchestrateur(client, moteur_entreprise, DATE_REFERENCE)
    resultat = graphe.invoke(
        _entree(EMAIL["menace-gros-montant"]), {"configurable": {"thread_id": "o4"}}
    )
    motifs = " ".join(resultat["motifs_escalade"])
    assert "300" in motifs and "juridique" in motifs
    assert resultat["action_proposee"] == {"type": "retour", "commande_id": "CMD-0003"}
    # L'agent de rédaction connaît les motifs d'escalade.
    assert "300" in client.appels[2]["messages"][-1]["content"]


def test_email_suspect_va_au_conseiller_sans_llm(moteur_entreprise):
    for construire in (construire_workflow, construire_orchestrateur):
        client = FauxClientLLM()
        graphe = construire(client, moteur_entreprise, DATE_REFERENCE)
        resultat = graphe.invoke(
            _entree(EMAIL["injection"]), {"configurable": {"thread_id": construire.__name__}}
        )
        assert "__interrupt__" in resultat and not client.appels
        assert not resultat.get("action_proposee")
        assert resultat["brouillon"].startswith("Bonjour")
        assert any("injection" in m for m in resultat["motifs_escalade"])


def test_orchestrateur_borne(moteur_entreprise):
    client = FauxClientLLM([_appel("agent_documentation", question="?"), "doc"] * 10)
    graphe = construire_orchestrateur(client, moteur_entreprise, DATE_REFERENCE, max_etapes=2)
    resultat = graphe.invoke(_entree(EMAIL["suivi"]), {"configurable": {"thread_id": "o3"}})
    assert "__interrupt__" in resultat and resultat["etapes"] == 2


def test_parcours_web(moteur_entreprise):
    from langgraph.checkpoint.memory import InMemorySaver

    from exemplia.app import creer_app
    from exemplia.socle.web import dep_client_llm, dep_moteur
    from exemplia.workflow_agents.web import dep_checkpointer

    faux = FauxClientLLM(
        [
            Classification(categorie="livraison", urgence="normale"),
            Extraction(
                commande_id="CMD-0021",
                demande="information",
                resume="suivi",
                menace_juridique=False,
            ),
            "Votre colis arrive bientôt.",
        ]
    )
    app = creer_app()
    app.dependency_overrides[dep_moteur] = lambda: moteur_entreprise
    app.dependency_overrides[dep_client_llm] = lambda: faux
    checkpointer = InMemorySaver()
    app.dependency_overrides[dep_checkpointer] = lambda: checkpointer
    http = TestClient(app)
    reponse = http.post("/workflow/traiter", data={**_entree(EMAIL["suivi"]), "mode": "workflow"})
    assert "Validation humaine" in reponse.text and "Votre colis arrive bientôt." in reponse.text
    identifiant = reponse.text.split('name="identifiant" value="')[1].split('"')[0]
    final = http.post(
        "/workflow/valider",
        data={"identifiant": identifiant, "texte": "Envoyé", "approuver": "true"},
    )
    assert "envoyee" in final.text
    # Un traitement déjà clos ne peut plus être validé.
    rejoue = http.post("/workflow/valider", data={"identifiant": identifiant, "approuver": "true"})
    assert rejoue.status_code == 404


def test_orchestrateur_refuse_une_action_inconnue(moteur_entreprise):
    client = FauxClientLLM(
        [
            _appel("proposer_action", type="remboursement", commande_id="CMD-0034"),
            "Terminé.",
            "Bonjour, un conseiller vous répondra.",
        ]
    )
    graphe = construire_orchestrateur(client, moteur_entreprise, DATE_REFERENCE)
    resultat = graphe.invoke(
        _entree(EMAIL["retour-produit-casse"]), {"configurable": {"thread_id": "o5"}}
    )
    assert not resultat.get("action_proposee")
    assert "Action inconnue" in client.appels[1]["messages"][-1]["content"]
