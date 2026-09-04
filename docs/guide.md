# Guide pas à pas — Comida / Migros

Automatiser les courses Migros Online depuis des exports **Kookd**, avec workflow **promo-first** (promos auto, favoris, push).

**Résumé :** Liste promo Migros → `promos` → Kookd (recettes) → `week` → push Migros.

---

## Workflow hebdomadaire (promo → Kookd → courses)

### Phase A — Ingrédients promo pour Kookd

1. Constituer une liste Migros avec les promos de la semaine (ex. **S1**).
2. Exporter les ingrédients filtrés (format liste simple) :

```bash
uv run python main.py promos --list S1
# Partager dans le topic Comida du groupe Telegram (coloc) :
uv run python main.py promos --list S1 --telegram
# ou : uv run python main.py promos S1 -o exports/promos-kookd.txt
```

3. Copier-coller le fichier généré dans **Kookd** pour proposer des recettes.
4. Choisir les recettes de la semaine dans Kookd.

**Filtres appliqués :** fruits, pain (sauf pâtes à pizza/tarte), sauces type ketchup, yaourts/desserts, plats préparés (sauf momos). Noms traduits en français. Règles manuelles dans `promo-filter.txt`.

### Phase B — Compléter les courses (Comida)

1. Exporter les recettes Kookd → `exports/semaine.txt`
2. Lancer le workflow courses :

```bash
uv run python main.py week exports/semaine.txt
```

3. Ajouter les favoris manquants sur Migros si besoin, puis pousser vers le panier.
4. Pousser vers Migros et checkout sur migros.ch.

---

## Telegram (topic Comida — coloc)

Partager la liste promo dans le groupe Telegram (ex. **Betty's coloc**, topic **Comida**).

**Guide détaillé (setup, dépannage, checklist) :** [telegram-setup.md](telegram-setup.md)

### Configuration rapide

1. Bot via [@BotFather](https://t.me/BotFather) → `TELEGRAM_BOT_TOKEN` dans `.env`
2. Group Privacy **off** (BotFather → Bot Settings)
3. Bot ajouté au groupe → message `@JeanThimBot test` dans le topic **Comida**
4. `uv run python validate.py telegram-setup` → copier les ids dans `.env`
5. `uv run python validate.py telegram-test`

### Utilisation

```bash
uv run python main.py promos --list S1 --telegram
uv run python validate.py send exports/promos-s1.txt
```

Variables optionnelles : `TELEGRAM_AUTO_SEND`, `TELEGRAM_SEND_ON_PUSH` (voir [telegram-setup.md](telegram-setup.md)).

---

## Prérequis

- macOS (testé) avec **Node.js 18+** et **Python 3.12+**
- Compte **Migros Online** (identifiants + 2FA TOTP si activée)
- Recettes planifiées dans **Kookd** (portions **8** configurées dans l’app)
- [uv](https://docs.astral.sh/uv/) pour Python

---

## Étape 0 — Installation (une fois)

Depuis la racine du projet :

```bash
cd /chemin/vers/Migros

# Python
uv sync

# Node (API Migros)
npm install
```

Copier la configuration :

```bash
cp .env.example .env
```

Éditer `.env` (voir étape 1). **Ne jamais committer `.env`.**

---

## Étape 1 — Configuration `.env`

| Variable | Obligatoire | Description |
|----------|-------------|-------------|
| `MIGROS_EMAIL` | Oui (pour `push`) | Email Migros Online |
| `MIGROS_PASSWORD` | Oui (pour `push`) | Mot de passe |
| `MIGROS_TOTP_SECRET` | Si 2FA | Seed base32 (pas le code 6 chiffres) |
| `MIGROS_SHOPPING_LIST_NAME` | Recommandé | Nom de la liste cible, ex. `Les Avengers` |
| `MIGROS_SHOPPING_LIST_ID` | Alternative | Id numérique (prioritaire sur le nom) |
| `MIGROS_LIST_SLUG` | Optionnel | Slug affiché après push (lien partagé) |
| `MIGROS_MIN_DELIVERY_CHF` | Optionnel | Seuil livraison pour l'estimation budget (défaut : 99) |

Lister vos listes et vérifier la cible :

```bash
uv run python validate.py lists
```

Exemple de sortie :

```
  id=81957373  name=Les Avengers  items=8  ← cible (.env NAME)
  id=68571113  name=Liste de Louis  items=19
```

Le **slug** d’un lien `https://www.migros.ch/list/xxxxx` n’est **pas** le même que `shoppingListId`.

Tester la connexion :

```bash
uv run python validate.py lists
```

Si erreur d’identifiants, corriger `.env`.

---

## Étape 2 — Garde-manger (optionnel, une fois + maintenance)

Fichier : `garde-manger.txt`

- Lignes normales = ingrédients **déjà en stock** (non ajoutés aux courses).
- Lignes `+` = **toujours acheter**, même si le garde-manger correspond.
- **Quantités** : `riz 2 kg`, `500 g farine` — le stock est déduit des besoins recette.

Exemple :

```text
riz 2 kg
vinaigre
huile en tout genre

# Toujours acheter
+ riz à sushi
```

---

## Étape 3 — Préparer la session (chaque semaine)

### Workflow recommandé : commande `week`

La commande unifiée analyse les exports, prend les promos et favoris automatiquement, et ouvre l’interface web :

```bash
# Un export (ou tout exports/*.txt si le dossier existe)
uv run python main.py week exports/semaine.txt

# Plusieurs recettes fusionnées
uv run python main.py week exports/lun.txt exports/mer.txt exports/ven.txt

# Sans ouvrir le navigateur (terminal seulement)
uv run python main.py week exports/semaine.txt --no-ui

# Adapter les portions (Kookd exporté pour 8, cuisiner pour 4)
uv run python main.py week exports/semaine.txt --portions 4

# Forcer le rafraîchissement des promos (sinon cache 24h)
uv run python main.py week exports/semaine.txt --refresh-promos

# Rouvrir l’interface sur la session en cours
uv run python main.py ui
```

**Ce que fait `week` :**

- Parse l’export Kookd (ou fusionne plusieurs exports)
- Applique le garde-manger (avec déduction des stocks)
- Indexe les promos Migros (cache local 24h, `--refresh-promos` pour forcer)
- **Charge vos favoris Migros** (Mes produits)
- Résout automatiquement les ingrédients **en promo** (favori s’il est en offre, sinon meilleure promo)
- Résout automatiquement les ingrédients avec un favori correspondant (hors promo)
- Calcule les **quantités panier** (paquets Migros selon besoin recette)
- Affiche une **estimation budget** et l’écart au minimum livraison
- Signale les ingrédients **sans favori ni promo** → à ajouter sur [migros.ch/fr/my-products](https://www.migros.ch/fr/my-products)
- Ouvre l’interface sur http://127.0.0.1:8765

Durée typique : ~20 s avec cache promos, ~45 s au premier scan.

### Alternative : `prepare` (CLI / Cursor)

```bash
uv run python main.py prepare exports/semaine.txt
```

Sans interface — utile pour le terminal / Cursor.

### 3.1 Dans Kookd

1. Sélectionner les recettes de la semaine.
2. Générer les portions pour **8 personnes** dans Kookd.
3. Exporter la liste d’ingrédients en **texte** (format lignes `- 200 g …`).

Sauver l’export, ex. `exports/semaine.txt`, ou utiliser l’exemple :

```bash
# Exemple fourni
examples/sushi_bowl.txt
```

### 3.2 Lancer l’analyse Comida

Voir **commande `week`** ci-dessus (recommandé) ou :

```bash
uv run python main.py prepare exports/semaine.txt
```

Ou sans argument (exemple sushi) :

```bash
uv run python main.py prepare
```

**Ce que fait `prepare` :**

- Parse l’export Kookd
- Applique le garde-manger
- Indexe les promos Migros de la semaine
- Résout automatiquement promos et favoris
- Crée `data/validation_session.json`
- Affiche l’état (favoris manquants, panier)

Durée typique : ~30–45 s (scan des promos).

---

## Étape 4 — Favoris manquants puis push

Après `week`, l’interface s’ouvre automatiquement. Sinon :

```bash
uv run python main.py ui
```

**Promos et favoris connus** : déjà dans le panier, rien à choisir.

**Favori manquant** → ajouter sur [Mes produits Migros](https://www.migros.ch/fr/my-products), puis **Recharger favoris** (ou `uv run python validate.py refresh`).

Quand tout est résolu, cliquer **Pousser vers Migros** (ou `uv run python validate.py push`).

Pour corriger un produit déjà choisi : `validate.py reopen <clé>` puis `search` / `accept`.

### Vérifier la progression

```bash
uv run python validate.py summary
```

---

## Étape 5 — Pousser vers Migros Online

Quand `summary` indique que tout est résolu :

```bash
uv run python validate.py push
```

Si des ingrédients sont encore en attente :

```bash
uv run python validate.py push --force
```

(`--force` pousse uniquement les **validés**, pas les en attente.)

**Résultat attendu :**

- Produits ajoutés à la liste configurée dans `.env`
- Lien checkout Migros
- `shoppingListId` affiché pour confirmation

---

## Étape 6 — Finaliser sur Migros (manuel)

1. Ouvrir [migros.ch](https://www.migros.ch) **connecté**.
2. Panier → sélectionner la **bonne liste** (ex. Les Avengers).
3. Vérifier les articles et **ajuster les quantités** (Comida ajoute 1 unité par ligne).
4. Passer commande : slot livraison, paiement.

Le checkout n’est **jamais** automatisé (sécurité / paiement).

---

## Référence rapide des commandes

| Commande | Usage |
|----------|--------|
| `uv run python main.py promos --list S1 --telegram` | Export promo + partage topic Comida |
| `uv run python main.py week <fichier(s)>` | **Workflow unifié** : analyse + favoris + interface |
| `uv run python main.py week … --portions 4` | Adapter les quantités (base Kookd : 8) |
| `uv run python main.py week … --refresh-promos` | Forcer le scan promos (ignore le cache) |
| `uv run python main.py ui` | Rouvrir l’interface sur la session en cours |
| `uv run python main.py prepare <fichier>` | Analyse + résolution auto (CLI) |
| `uv run python validate.py show` | Afficher la session |
| `uv run python validate.py summary` | État + liste résolue + budget |
| `uv run python validate.py basket` | Panier détaillé (noms, quantités, prix) |
| `uv run python validate.py favorites` | Lister vos favoris Migros |
| `uv run python validate.py refresh` | Recharger favoris après ajout sur Migros |
| `uv run python validate.py reopen <clé>` | Rouvrir un produit pour le corriger |
| `uv run python validate.py search <clé> <terme>` | Recherche Migros (correction) |
| `uv run python validate.py accept <clé> <n°>` | Confirmer après search/reopen |
| `uv run python validate.py push` | Envoyer au panier Migros |
| `uv run python validate.py telegram-setup` | Configurer le groupe / topic Telegram |
| `uv run python validate.py telegram-test` | Message de test dans le topic Comida |
| `uv run python validate.py send <fichier>` | Envoyer un export sur Telegram |

---

## Fichiers importants

| Fichier | Rôle |
|---------|------|
| `garde-manger.txt` | Stock maison (quantités) + exceptions `+` |
| `data/promo_cache.json` | Cache promos Migros (TTL 24h) |
| `data/validation_session.json` | Session courante de validation |
| `mappings.json` | Choix mémorisés (uid, backups, refus) |
| `.env` | Identifiants et liste cible (secret) |
| `examples/sushi_bowl.txt` | Exemple d’export Kookd |

---

## Dépannage

### `Identifiants Migros requis`

Remplir `MIGROS_EMAIL` et `MIGROS_PASSWORD` dans `.env`, puis `uv run python validate.py lists`.

### `Liste « … » introuvable`

```bash
uv run python validate.py lists
```

Corriger `MIGROS_SHOPPING_LIST_NAME` ou utiliser `MIGROS_SHOPPING_LIST_ID`.

### Erreur sur un lien `/list/xxxxx`

- Le slug du lien partagé ≠ `shoppingListId`.
- Migros peut être en maintenance → utiliser le panier connecté sur migros.ch.

### `reject` / `search` (corrections)

Le flux hebdo n’utilise plus `accept`/`reject`. Pour corriger un produit : `reopen <clé>` puis `search` / `accept`.

### Minimum de commande non atteint

Migros Online exige souvent ~99 CHF pour la livraison. Ajouter des articles ou commander plus de recettes.

### Promos / M-Budget dans les résultats `search`

Vérifier les numéros d’option ; ne pas choisir M-Budget. Filtrage à améliorer dans une version future.

---

## Workflow type (dimanche)

```bash
# 1. Export promo → Kookd (choisir recettes)
uv run python main.py promos --list S1

# 2. Export Kookd → exports/semaine.txt

# 3. Analyse (promos + favoris auto, cache promos)
uv run python main.py week exports/semaine.txt

# 4. Ajouter les favoris manquants sur migros.ch/fr/my-products si besoin
uv run python validate.py refresh

# 5. Vérifier le panier et le budget
uv run python validate.py basket

# 6. Pousser depuis l’interface ou :
uv run python validate.py push

# 7. Checkout sur migros.ch
```

---

Voir aussi : [changelog.md](../changelog.md) pour l’historique des fonctionnalités.
