# Changelog — Comida / Migros

Automatisation des courses Migros Online depuis des exports Kookd, avec workflow **promo-first** (promos auto, favoris, push).

---

## Vision initiale

- Automiser les courses hebdomadaires Migros en profitant des **promos** et des points Cumulus.
- Recettes exportées depuis [Kookd](https://kookd.app) (texte), planning hebdo restant dans Kookd.
- Commande via Migros Online, portions 8 dans Kookd, exclusion **M-Budget**.
- Documentation et pistes techniques sur la page Notion **Comida** (migros-mcp, migros-api-wrapper, etc.).

---

## 2026-09-02 — Prototype et pipeline promo-first

### Infrastructure projet

- Projet Python **`comida`** géré avec **uv** (`pyproject.toml`, `uv.lock`).
- Package `src/comida/` : modules parser, pantry, matcher, pipeline, client Migros.
- Pont Node.js **`scripts/migros.mjs`** vers `migros-api-wrapper` (promos, recherche, détails produits).
- Dépendances Node : `migros-api-wrapper`, `migros-mcp` (`package.json`).
- Exemple recette : `examples/sushi_bowl.txt`.
- Fichiers maison : `garde-manger.txt`, `contexte.txt`.

### Parseur Kookd

- Lecture des lignes `- 200 g Lardons fumés`, `- 3 pincée Sel et poivre`, etc.
- Extraction quantité, unité, nom d’ingrédient (`src/comida/parser.py`).

### Garde-manger

- Filtrage des ingrédients déjà en stock via `garde-manger.txt`.
- Matching par mot-clé avec garde-fous (ex. **nori** ≠ **riz**).
- Lignes `+` pour **toujours acheter** même si le garde-manger correspond (ex. `+ riz à sushi` vs `riz` générique).

### Matching Migros (promo-first)

- Index des **~1224 promos** Migros Online de la semaine.
- Pour chaque ingrédient : match promo puis recherche catalogue.
- Exclusion **M-Budget**, produits non-alimentaires, plats préparés inadaptés.
- Synonymes **FR/DE** (concombre → gurke, courgette → zucchetti, lardons → speck, etc.).
- Scoring fuzzy (`rapidfuzz`), cas ambigus signalés.

### CLI principale

- `uv run python main.py prepare <recette>` — analyse promos + matching, crée la session de validation.

---

## 2026-09-02 — Validation conversationnelle (option C)

### Session et mappings

- `data/validation_session.json` — file de validation pour l’agent / le chat.
- `mappings.json` — choix mémorisés (`accepted_uid`, `backup_uid`, `rejected_uids`).
- Format agent : options numérotées, **promos à valider** comme le catalogue.

### `validate.py`

| Commande | Rôle |
|----------|------|
| `show` | Affiche la session pour validation dans Cursor |
| `accept <clé> <n°>` | Confirme un produit (+ backup automatique) |
| `reject <clé>` | Refuse l’option courante → propose le backup suivant |
| `search <clé> <terme>` | Recherche Migros manuelle |
| `reopen <clé>` | Rouvre un ingrédient déjà validé pour corriger |
| `summary` | Liste panier validé |
| `lists` | Liste les shopping lists du compte |
| `push` | Pousse les validés vers Migros Online |

- `search` rouvre automatiquement un ingrédient déjà dans `resolved` si besoin de correction.
- Règle Cursor : `.cursor/rules/comida-validation.mdc`.

---

## 2026-09-02 — Panier Migros Online (push)

### Authentification

- `.env` / `.env.example` : `MIGROS_EMAIL`, `MIGROS_PASSWORD`, `MIGROS_TOTP_SECRET`.
- Chargement `.env` côté Python et `scripts/migros-basket.mjs`.

### Cible de liste configurable

- `MIGROS_SHOPPING_LIST_ID` — id numérique (`shoppingListId`).
- `MIGROS_SHOPPING_LIST_NAME` — ex. `Les Avengers`, `Liste de Louis`.
- Correction API : champ `shoppingListName` (et `itemsCount`), pas `name`.
- `MIGROS_LIST_SLUG` — slug affiché après push (lien partagé ; distinct de l’id API).

### Script panier

- **`scripts/migros-basket.mjs`** — `lists`, `basket`, `add`, `push` via `migros-mcp`.
- **`src/comida/basket.py`** — wrapper Python.
- `push` avec garde-fou si ingrédients encore en attente (`--force` pour ignorer).
- Checkout toujours **manuel** dans le navigateur (pas de commande auto).

---

## Tests réels (session du 2 sept.)

- Recette sushi 8 portions : 8 ingrédients validés après corrections (crème, avocat, etc.).
- Push réussi vers la liste **Les Avengers** (`shoppingListId` 81957373).
- Listes du compte identifiées : **Liste de Louis** (19), **Les Avengers** (8), **test__liste** (4).

---

## Limites connues

| Sujet | Statut |
|-------|--------|
| API Migros | Non officielle, peut changer ou être bloquée (Cloudflare) |
| Lien partagé `/list/<slug>` | Non lisible par slug sans reverse ; maintenance Migros fréquente |
| Noms produits dans le panier API | Nécessitent un 2e appel `get_product_details` par uid |
| Quantités push | 1 unité par ligne (ajustement manuel sur migros.ch) |
| Recherche `search` | Peut inclure M-Budget / hors-sujet ; filtrage à renforcer |
| Checkout link après `push` | Peut refléter la liste par défaut du compte, pas toujours la liste cible |

---

## 2026-09-02 — Interface web + commande `week`

### Commande unifiée `week`

- `uv run python main.py week [fichiers…]` — prepare + résolution favoris + interface web.
- Fusion multi-recettes : `week exports/lun.txt exports/mer.txt`.
- Options : `--no-ui`, `--port 8765`.
- `uv run python main.py ui` — rouvrir l’interface sur la session en cours.

### Interface web intégrée

- Serveur local `http://127.0.0.1:8765` (`src/comida/ui/`).
- Validation visuelle, push Migros, bouton **Recharger favoris**.
- Dossier `exports/` pour déposer les exports Kookd.

---

## 2026-09-03 — Workflow favoris Migros

### Favoris comme source de vérité (remplace l’auto-accept `mappings.json`)

- Lecture des **favoris Migros** (`GET /shopping/public/v3/favorites/products`) via `scripts/migros-favorites.mjs`.
- Ingrédient avec favori correspondant → **résolu automatiquement** (hors promo).
- Aucun favori → `needs_favorite` : ajouter sur [migros.ch/fr/my-products](https://www.migros.ch/fr/my-products), puis `validate.py refresh`.
- **Promos** seules en validation manuelle (`reject` = garder le favori habituel).

### Nouvelles commandes `validate.py`

| Commande | Rôle |
|----------|------|
| `favorites` | Liste les favoris Migros (uid, nom, prix) |
| `refresh` | Recharge les favoris et réapplique le workflow sur la session |

### Session enrichie

- Champs `needs_favorite`, `favorites_resolved`, `favorites_count`.
- Règle Cursor mise à jour : `.cursor/rules/comida-validation.mdc`.

---

## 2026-09-03 — Export promo → Kookd (workflow inversé)

### Commande `promos`

- `uv run python main.py promos --list S1` — exporte les ingrédients d’une **liste Migros** (pas de scan promo complet).
- Sortie format A (une ligne par ingrédient) → copier-coller dans Kookd pour générer des recettes.
- Fichier généré : `exports/promos-<liste>.txt`.
- Options : `-o <fichier>`, `--pantry` (optionnel).

### Filtres automatiques

- **Exclus** : fruits (sauf exceptions), pain (sauf pâtes pizza/tarte), sauces condiment, yaourts/desserts, plats préparés, M-Budget, boissons/snacks.
- **Inclus** : momos (accompagnés de riz + sauce à cuisiner), fromages avec description (ex. mozzarella pour pizza).
- **Exceptions fruits salés** : avocat (salade, guacamole).
- Libellés enrichis via `breadcrumb` Migros (ex. tomates en conserve pelées et hachées).
- Traduction **DE → FR** (`src/comida/de_fr.py`).
- Overrides manuels : `promo-filter.txt` (`+ momos`, `+ avocat`, etc.).

### Workflow hebdomadaire documenté

1. Liste promo Migros (ex. **S1**) → `promos` → Kookd (recettes)
2. Export recettes Kookd → `week` → favoris + promos → push Migros

---

## 2026-09-04 — Plus de validation manuelle des promos

- Les **promos** sont prises automatiquement (favori s’il est en offre, sinon meilleure promo du matching).
- Hors promo : favori Migros comme avant.
- Seul geste restant : ajouter un favori manquant sur [Mes produits](https://www.migros.ch/fr/my-products), puis `validate.py refresh`.
- `accept` / `reject` restent disponibles pour une **correction** (`reopen`), plus pour le flux hebdo.

---

## Pistes non implémentées

- Cache promos / mappings pour accélérer `week`.
- `validate.py basket` — afficher la liste Migros enrichie (noms + prix) pour l’agent.
- Liaison automatique slug partagé ↔ `shoppingListId`.
- Intégration migros-mcp native dans Cursor (outils MCP en plus du CLI).
