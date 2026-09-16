"""Sessions de conversation du service client, stockées en base.

L'état d'une conversation (historique, action en attente de confirmation, escalade) survit ainsi au
redémarrage de l'application et reste cohérent quand plusieurs processus servent les requêtes.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime

from sqlalchemy import Engine, select, update

from exemplia.service_client.assistant import ActionEnAttente, Session
from exemplia.socle import base_donnees as bd


class SessionInconnue(KeyError):
    pass


class DepotSessions:
    def __init__(self, moteur: Engine) -> None:
        self.moteur = moteur
        bd.sessions_assistant.create(moteur, checkfirst=True)

    def charger(self, session_id: str) -> Session:
        with self.moteur.connect() as cx:
            ligne = cx.execute(
                select(bd.sessions_assistant).where(bd.sessions_assistant.c.id == session_id)
            ).first()
        if ligne is None:
            raise SessionInconnue(session_id)
        donnees = json.loads(ligne.donnees)
        action = donnees["action_en_attente"]
        return Session(
            client_id=ligne.client_id,
            id=ligne.id,
            historique=donnees["historique"],
            resultats_outils=donnees.get("resultats_outils", []),
            action_en_attente=ActionEnAttente(**action) if action else None,
            escalade=donnees["escalade"],
        )

    def enregistrer(self, session: Session) -> None:
        valeurs = {
            "client_id": session.client_id,
            "donnees": json.dumps(
                {
                    "historique": session.historique,
                    "resultats_outils": session.resultats_outils,
                    "action_en_attente": (
                        asdict(session.action_en_attente) if session.action_en_attente else None
                    ),
                    "escalade": session.escalade,
                },
                ensure_ascii=False,
                default=str,
            ),
            "mise_a_jour": datetime.now(),
        }
        with self.moteur.begin() as cx:
            modifiees = cx.execute(
                update(bd.sessions_assistant)
                .where(bd.sessions_assistant.c.id == session.id)
                .values(**valeurs)
            ).rowcount
            if not modifiees:
                cx.execute(bd.sessions_assistant.insert().values(id=session.id, **valeurs))
