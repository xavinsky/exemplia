# Exemplia — site

Site statique publié sur https://tekio.org/exemplia/ : présentation des exemples, leur documentation,
l'architecture et l'installation. Le texte n'est pas écrit pour le site : chaque page lit un fichier
Markdown du dépôt (README des modules, `comment-ca-marche.md`, `doc/*.md`), qui reste la seule source
et se lit aussi bien sur GitHub. Moteur repris d'AmeliorIA : compilation par `build/build.py` en
`www/data/content.js`, plus une page HTML statique par section pour le référencement.

```bash
make site                 # depuis la racine du dépôt : build, puis ouvrir site/www/index.html
```

Publication : `.github/workflows/site.yml` construit le site et le déploie sur GitHub Pages à chaque
push sur `main`.

| Élément | Rôle |
|---|---|
| `content/site.yml` | Onglets, groupes du menu, pour un groupe la liste des modules de `src/exemplia/` publiés, et les autres projets IA de tekio.org listés dans le menu de l'Accueil |
| `content/<onglet>/<groupe>/<NN>-<slug>.md` | Une section : texte propre au site, ou renvoi vers un fichier du dépôt (`source: doc/installation.md`), le texte du fichier s'ajoutant alors à la fin |
| `content/lexique.md` | Un terme par titre `## Terme`, avec un lien vers la section qui le détaille |
| `build/build.py` | Compilation, réécriture des liens et des images, contrôle des liens internes, pages statiques, `sitemap.xml` |
| `www/` | `index.html` (gabarit), `engine.js`, `style.css` ; `data/`, `media/`, les pages `<id>.html` et `sitemap.xml` sont produits par le build et ne sont pas versionnés |

## Pages d'un module

Pour chaque module listé dans `site.yml` :

| Page | Id | Source |
|---|---|---|
| Présentation | `<module>` (`_` remplacé par `-`) | `src/exemplia/<module>/README.md`, titre de premier niveau retiré |
| Comment ça marche ? | `<module>-fonctionnement` | `comment-ca-marche.md` (texte affiché par l'application) puis `fonctionnement.md` (schéma de composants, choix techniques) |
| Comment utiliser ? | `<module>-utilisation` | `utilisation.md` : commandes, scénarios de démonstration, fichiers du module |
| Évaluation | `<module>-evaluation` | `evaluation.md` : commande, jeu de test, résultats, comparaisons de modèles |

Chaque fichier est facultatif : une page sans fichier n'est pas publiée. Les pages s'ouvrent sur un lien vers le répertoire du module sur GitHub. Le bandeau du site porte
le lien vers la racine du dépôt.

Le schéma de composants de chaque exemple est le bloc Mermaid de la section « Composants de
l'exemple » de son `fonctionnement.md` : flux numérotés ①②③…, expliqués dans la liste qui suit le schéma, et
quatre classes de nœuds (`code` pour le processus Python, `gpu` pour ce qui calcule sur la carte,
`disque` pour les stockages, `externe` pour les services hors machine). GitHub et le site
dessinent le même bloc.

## Liens et images

- Un lien vers un fichier Markdown publié devient un lien interne (`#id`, ou `#id--titre` pour une
  ancre) ; le build échoue si la cible n'existe pas.
- Un lien vers un autre fichier du dépôt mène à ce fichier sur GitHub.
- Les images sont copiées dans `www/media/` ; une image seule dans son paragraphe devient une
  capture cliquable, avec son texte alternatif pour légende.
