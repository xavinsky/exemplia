"""Fine-tuning de CamemBERT v2 pour le tri des tickets, suivi dans MLflow (GPU requis).

    uv sync --group gpu
    uv run python -m exemplia.tri_tickets.fine_tuning

    uv run python -m exemplia.tri_tickets.fine_tuning --promouvoir

Le run rejoint l'expérience `tri-tickets` avec les mêmes métriques que les autres approches.
`--promouvoir` rejoue la règle de promotion sur tous les runs de l'expérience, fine-tuning compris.
"""

from __future__ import annotations

import argparse
import time

import mlflow
import numpy as np

from exemplia.socle.config import parametres
from exemplia.tri_tickets.experiences import (
    EXPERIENCE,
    jeu_de_donnees,
    promouvoir_champion,
    resultats_experience,
)
from exemplia.tri_tickets.modeles import CATEGORIES_TICKETS

# CamemBERT v1 : le tokenizer de `camembertv2-base` n'est pas chargé correctement par
# transformers 5.x (le texte est découpé caractère par caractère), ce qui empêche l'apprentissage.
MODELE_BASE = "almanach/camembert-base"


def main() -> None:
    import torch
    from datasets import Dataset
    from sklearn.metrics import accuracy_score, f1_score
    from transformers import (
        AutoModelForSequenceClassification,
        AutoTokenizer,
        Trainer,
        TrainingArguments,
        pipeline,
    )

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--epoques", type=int, default=20)
    parser.add_argument("--taux", type=float, default=5e-5)
    parser.add_argument("--lot", type=int, default=16)
    parser.add_argument("--graine", type=int, default=42)
    parser.add_argument(
        "--promouvoir",
        action="store_true",
        help="Compare tous les runs de l'expérience et met à jour l'alias champion",
    )
    args = parser.parse_args()

    if not torch.cuda.is_available():
        raise SystemExit("Aucun GPU CUDA disponible.")

    mlflow.set_tracking_uri(parametres().mlflow_tracking_uri)
    mlflow.set_experiment(EXPERIENCE)
    donnees = jeu_de_donnees()
    id_de = {c: i for i, c in enumerate(CATEGORIES_TICKETS)}

    tokenizer = AutoTokenizer.from_pretrained(MODELE_BASE)
    modele = AutoModelForSequenceClassification.from_pretrained(
        MODELE_BASE,
        num_labels=len(CATEGORIES_TICKETS),
        id2label=dict(enumerate(CATEGORIES_TICKETS)),
        label2id=id_de,
    )

    def jeu(textes, etiquettes):
        brut = Dataset.from_dict({"text": textes, "label": [id_de[e] for e in etiquettes]})
        return brut.map(
            lambda lot: tokenizer(lot["text"], truncation=True, max_length=128), batched=True
        )

    def metriques(prediction):
        predits = np.argmax(prediction.predictions, axis=-1)
        return {
            "f1_macro": f1_score(prediction.label_ids, predits, average="macro"),
            "exactitude": accuracy_score(prediction.label_ids, predits),
        }

    entrainement = TrainingArguments(
        output_dir=str(parametres().modeles_dir / "camembert-tri-tickets"),
        num_train_epochs=args.epoques,
        learning_rate=args.taux,
        per_device_train_batch_size=args.lot,
        per_device_eval_batch_size=64,
        eval_strategy="epoch",
        save_strategy="no",
        # 239 tickets d'entraînement : la montée en charge du taux évite les premiers pas erratiques.
        warmup_steps=20,
        seed=args.graine,
        bf16=torch.cuda.is_bf16_supported(),
        report_to="none",
    )
    trainer = Trainer(
        model=modele,
        args=entrainement,
        train_dataset=jeu(donnees.x_train, donnees.y_train),
        eval_dataset=jeu(donnees.x_test, donnees.y_test),
        processing_class=tokenizer,
        compute_metrics=metriques,
    )

    with mlflow.start_run(run_name="camembert-fine-tuning"):
        mlflow.log_params(
            {
                "approche": "camembert",
                "modele_base": MODELE_BASE,
                "epoques": args.epoques,
                "taux": args.taux,
                "lot": args.lot,
                "graine": args.graine,
                "n_train": len(donnees.x_train),
            }
        )
        trainer.train()
        classifieur = pipeline(
            "text-classification", model=trainer.model, tokenizer=tokenizer, device=0
        )
        debut = time.perf_counter()
        predictions = [p["label"] for p in classifieur(donnees.x_test, batch_size=64)]
        latence_ms = (time.perf_counter() - debut) * 1000 / len(donnees.x_test)
        mlflow.log_metrics(
            {
                "f1_macro": f1_score(donnees.y_test, predictions, average="macro"),
                "exactitude": accuracy_score(donnees.y_test, predictions),
                "latence_ms_par_ticket": latence_ms,
            }
        )
        mlflow.transformers.log_model(
            transformers_model=classifieur, name="modele", task="text-classification"
        )

    if args.promouvoir:
        gagnant, version = promouvoir_champion(resultats_experience())
        print(f"Champion : {gagnant.approche} (version {version})")


if __name__ == "__main__":
    main()
