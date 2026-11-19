# Évaluation

## Évaluation

`uv run python -m exemplia.llmops.evaluer service_client` : outils appelés, action proposée,
escalade, et juge sur les consignes (voir [llmops](../llmops/README.md)).

Avec `qwen3.5:9b` et le juge `gemma4:12b`, sur les 13 demandes du jeu : consignes 1,0, mentions
attendues 1,0, action correcte 0,92, escalade correcte 0,91, outils attendus 0,80.

Les écarts restants viennent du modèle, pas du code, et deux comportements distincts s'y cachent :

- une réponse où le modèle invente un détail (une date de livraison sur une commande qui n'est pas
  livrée) : le juge la bloque et la conversation part chez un conseiller. La garde joue son rôle ;
- une demande de retour traitée sans appeler `proposer_retour`, malgré la consigne : le modèle
  répond à partir du statut qu'il voit dans son contexte. C'est la contrepartie du contexte décrite
  plus haut, et elle n'est pas éliminée, seulement réduite.

Ces résultats supposent le juge de sortie alimenté par les résultats des outils. Sans eux, il traite
les statuts et dates issus de la base comme des inventions et bloque la majorité des réponses.
