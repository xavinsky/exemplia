# Fonctionnement

## Points clés

- Authentification par Application Default Credentials : aucune clé dans le code ni dans `.env`.
- Sortie structurée : `response_mime_type="application/json"` et `response_schema` (classe
  Pydantic), résultat dans `reponse.parsed`.
- Consommation : `usage_metadata` donne les jetons d'entrée et de sortie, à suivre pour le coût.

Aucun test automatisé n'appelle ce script : le service est payant.
