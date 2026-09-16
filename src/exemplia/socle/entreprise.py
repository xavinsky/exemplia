"""Génération déterministe et chargement des données de l'Entreprise Exemple.

Les dates sont calculées par rapport à une date de référence (aujourd'hui par défaut) pour que les
règles métier (délai de retour, commande annulable...) restent pertinentes quel que soit le jour
où l'on lance les démonstrations.
"""

from __future__ import annotations

import argparse
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import Engine, delete, insert

from exemplia.socle import base_donnees as bd

GRAINE = 42
CATEGORIES_TICKETS = ["livraison", "retour", "facturation", "compte", "produit"]

PRODUITS = [
    ("P01", "Produit A", "produit", "19.90"),
    ("P02", "Produit B", "produit", "34.50"),
    ("P03", "Produit C", "produit", "49.00"),
    ("P04", "Produit D", "produit", "89.00"),
    ("P05", "Produit E", "produit", "129.00"),
    ("P06", "Produit F", "produit", "12.00"),
    ("P07", "Produit G", "produit", "249.00"),
    ("P08", "Accessoire H", "produit", "9.90"),
    ("A01", "Abonnement standard", "abonnement", "9.99"),
    ("A02", "Abonnement premium", "abonnement", "24.99"),
]

# Plusieurs formulations par catégorie, dont des demandes qui touchent deux sujets (un retour et
# son remboursement, une livraison et sa facturation) : la catégorie est celle du sujet principal.
_MODELES_TICKETS = {
    "livraison": [
        "Ma commande {cmd} n'est toujours pas arrivée, pouvez-vous me dire où elle en est ?",
        "Le colis de la commande {cmd} est indiqué livré mais je n'ai rien reçu.",
        "Quel est le délai de livraison pour le {produit} ?",
        "Le suivi de ma commande {cmd} ne bouge plus depuis plusieurs jours.",
        "Est-il possible de modifier l'adresse de livraison de la commande {cmd} ?",
        "Le livreur est passé en mon absence, comment récupérer mon colis ?",
        "J'ai reçu seulement une partie de ma commande {cmd}, où est le reste ?",
        "Livrez-vous le samedi ? J'attends le {produit}.",
        "Toujours rien reçu alors que j'ai payé il y a dix jours.",
        "Le transporteur dit que l'adresse est introuvable pour {cmd}.",
        "Mon voisin a réceptionné le paquet mais il est ouvert, le {produit} est-il bien dedans ?",
        "J'ai payé la livraison express et la commande {cmd} n'est pas arrivée plus vite.",
        "Vous expédiez en Belgique ?",
        "Le point relais a fermé, où est passé mon colis ?",
    ],
    "retour": [
        "Je souhaite retourner le {produit} reçu avec la commande {cmd}.",
        "Comment faire un retour ? Le {produit} ne me convient pas.",
        "J'ai renvoyé la commande {cmd} il y a deux semaines, quand serai-je remboursé ?",
        "Le {produit} est arrivé cassé, je veux le renvoyer.",
        "Puis-je échanger le {produit} contre un autre modèle ?",
        "Quel est le délai pour retourner un article ?",
        "Je n'ai pas reçu l'étiquette de retour pour la commande {cmd}.",
        "Mon retour a été refusé, je ne comprends pas pourquoi.",
        "Le {produit} ne correspond pas à la photo, je le rends.",
        "Erreur de taille sur {cmd}, je voudrais l'autre modèle à la place.",
        "J'ai déposé le paquet retour au bureau de poste, vous l'avez reçu ?",
        "Je me suis trompé en commandant le {produit}, je peux le renvoyer sans l'ouvrir ?",
        "Le remboursement de mon retour ne correspond pas au montant payé.",
        "Faut-il le carton d'origine pour renvoyer le {produit} ?",
    ],
    "facturation": [
        "J'ai été débité deux fois pour la commande {cmd}.",
        "Pouvez-vous m'envoyer la facture de la commande {cmd} ?",
        "Le montant prélevé ne correspond pas au prix du {produit}.",
        "Mon abonnement a été renouvelé alors que je l'avais résilié.",
        "Je voudrais changer de moyen de paiement pour mon abonnement.",
        "La facture indique une mauvaise adresse, pouvez-vous la corriger ?",
        "Un code promo n'a pas été appliqué sur la commande {cmd}.",
        "Pourquoi y a-t-il des frais supplémentaires sur ma facture ?",
        "On m'a facturé la livraison alors que la commande {cmd} dépassait 50 euros.",
        "Ma carte a été refusée mais la commande {cmd} apparaît quand même.",
        "Il me faut une facture au nom de ma société.",
        "Le prélèvement de l'abonnement premium est passé deux fois ce mois-ci.",
        "Je n'ai jamais souscrit d'abonnement et je suis prélevé tous les mois.",
        "Vous acceptez le paiement en plusieurs fois pour le {produit} ?",
    ],
    "compte": [
        "Je n'arrive plus à me connecter à mon compte.",
        "Comment changer l'adresse email associée à mon compte ?",
        "Je souhaite supprimer mon compte et mes données.",
        "Je ne reçois pas l'email de réinitialisation du mot de passe.",
        "Mon compte a été bloqué après plusieurs tentatives.",
        "Comment modifier mes préférences de communication ?",
        "Quelqu'un a peut-être accédé à mon compte sans autorisation.",
        "Je voudrais obtenir une copie de mes données personnelles.",
        "Arrêtez de m'envoyer des newsletters.",
        "Le site me dit que mon email est déjà utilisé alors que je n'ai pas de compte.",
        "Je ne retrouve plus l'historique de mes commandes dans mon espace.",
        "Comment ajouter une deuxième adresse dans mon profil ?",
        "J'ai reçu un email de connexion que je n'ai pas demandé.",
        "Mon mot de passe ne marche plus depuis la mise à jour du site.",
    ],
    "produit": [
        "Le {produit} est-il compatible avec l'{accessoire} ?",
        "Quelles sont les dimensions du {produit} ?",
        "Le {produit} sera-t-il de nouveau disponible bientôt ?",
        "Comment utiliser correctement le {produit} ?",
        "Quelle est la différence entre l'abonnement standard et premium ?",
        "Le {produit} fonctionne mal depuis quelques jours, que faire ?",
        "Existe-t-il une garantie sur le {produit} ?",
        "Pouvez-vous me conseiller entre le {produit} et le Produit C ?",
        "Le {produit} fait un bruit bizarre quand je l'allume.",
        "Où trouver la notice du {produit} ?",
        "Le {produit} chauffe beaucoup, est-ce normal ?",
        "Y a-t-il des pièces détachées pour le {produit} ?",
        "Le {produit} que j'ai reçu de la commande {cmd} ne s'allume pas du tout.",
        "L'abonnement premium donne accès à quoi de plus exactement ?",
    ],
}

_FORMULES = ["", "", "Bonjour, ", "Bonjour, ", "Madame, Monsieur, ", "Salut, ", "bjr "]
_CONCLUSIONS = ["", "", " Merci.", " Merci d'avance.", " Cordialement.", " C'est urgent.", " svp"]


@dataclass
class DonneesEntreprise:
    produits: list[dict] = field(default_factory=list)
    clients: list[dict] = field(default_factory=list)
    commandes: list[dict] = field(default_factory=list)
    lignes_commande: list[dict] = field(default_factory=list)
    tickets: list[dict] = field(default_factory=list)


def generer(reference: date | None = None, nb_commandes: int = 60, nb_tickets: int = 300):
    reference = reference or date.today()
    rng = random.Random(GRAINE)
    d = DonneesEntreprise()

    d.produits = [
        {"id": i, "libelle": lib, "type": t, "prix": Decimal(prix)} for i, lib, t, prix in PRODUITS
    ]
    d.clients = [
        {"id": f"C{n:02d}", "nom": f"Client {n:02d}", "email": f"client{n:02d}@exemple.test"}
        for n in range(1, 21)
    ]

    for n in range(1, nb_commandes + 1):
        age = rng.randint(0, 90)
        date_commande = reference - timedelta(days=age)
        statut, date_livraison = _statut_selon_age(rng, age, date_commande)
        commande_id = f"CMD-{n:04d}"
        montant = Decimal("0")
        for produit in rng.sample(d.produits, rng.randint(1, 3)):
            quantite = 1 if produit["type"] == "abonnement" else rng.randint(1, 3)
            montant += produit["prix"] * quantite
            d.lignes_commande.append(
                {
                    "commande_id": commande_id,
                    "produit_id": produit["id"],
                    "quantite": quantite,
                    "prix_unitaire": produit["prix"],
                }
            )
        d.commandes.append(
            {
                "id": commande_id,
                "client_id": rng.choice(d.clients)["id"],
                "date_commande": date_commande,
                "date_livraison": date_livraison,
                "statut": statut,
                "montant": montant,
            }
        )

    libelles = [p["libelle"] for p in d.produits if p["type"] == "produit"]
    for n in range(1, nb_tickets + 1):
        categorie = CATEGORIES_TICKETS[(n - 1) % len(CATEGORIES_TICKETS)]
        numero_modele = rng.randrange(len(_MODELES_TICKETS[categorie]))
        corps = _MODELES_TICKETS[categorie][numero_modele].format(
            cmd=rng.choice(d.commandes)["id"],
            produit=rng.choice(libelles),
            accessoire="Accessoire H",
        )
        texte = _bruiter(rng, rng.choice(_FORMULES) + corps + rng.choice(_CONCLUSIONS))
        d.tickets.append(
            {
                "id": n,
                "texte": texte,
                "categorie": categorie,
                "modele": f"{categorie}-{numero_modele}",
            }
        )
    rng.shuffle(d.tickets)
    return d


_SANS_ACCENT = str.maketrans("éèêëàâîïôûùç", "eeeeaaiiouuc")


def _bruiter(rng: random.Random, texte: str) -> str:
    """Imperfections des vrais messages : minuscules, accents absents, fautes de frappe."""
    if rng.random() < 0.3:
        texte = texte.lower()
    if rng.random() < 0.3:
        texte = texte.translate(_SANS_ACCENT)
    if rng.random() < 0.4:
        lettres = list(texte)
        for _ in range(rng.randint(1, 3)):
            i = rng.randrange(1, len(lettres) - 1)
            if rng.random() < 0.5:
                lettres[i], lettres[i + 1] = lettres[i + 1], lettres[i]
            else:
                del lettres[i]
        texte = "".join(lettres)
    return texte


def _statut_selon_age(rng: random.Random, age: int, date_commande: date):
    if age < 3:
        return "en_preparation", None
    if age < 7:
        return rng.choice(["en_preparation", "expediee", "annulee"]), None
    livraison = date_commande + timedelta(days=rng.randint(3, 6))
    if age < 12:
        statut = rng.choice(["expediee", "livree"])
        rng.random()  # tirage conservé pour garder la même séquence pseudo-aléatoire
        return statut, livraison if statut == "livree" else None
    statut = rng.choices(["livree", "retournee", "annulee"], weights=[8, 1, 1])[0]
    return statut, (None if statut == "annulee" else livraison)


def charger(moteur_: Engine, donnees: DonneesEntreprise) -> None:
    """Recrée le contenu des tables à partir des données générées."""
    bd.creer_schema(moteur_)
    with moteur_.begin() as cx:
        for table in reversed(bd.metadata.sorted_tables):
            cx.execute(delete(table))
        cx.execute(insert(bd.produits), donnees.produits)
        cx.execute(insert(bd.clients), donnees.clients)
        cx.execute(insert(bd.commandes), donnees.commandes)
        cx.execute(insert(bd.lignes_commande), donnees.lignes_commande)
        # `modele` (formulation d'origine) sert à séparer entraînement et test, pas à la base.
        cx.execute(
            insert(bd.tickets),
            [{k: t[k] for k in ("id", "texte", "categorie")} for t in donnees.tickets],
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Charge les données de l'Entreprise Exemple.")
    parser.add_argument("--reference", type=date.fromisoformat, default=None)
    args = parser.parse_args()
    donnees = generer(args.reference)
    charger(bd.moteur(), donnees)
    print(
        f"{len(donnees.clients)} clients, {len(donnees.commandes)} commandes, "
        f"{len(donnees.tickets)} tickets chargés."
    )


if __name__ == "__main__":
    main()
