# Telegram — setup bot & topic Comida

Guide de référence pour partager les exports Comida dans un **groupe Telegram avec topics** (ex. **Betty's coloc** → topic **Comida**).

**Pas besoin du lien du groupe** : le bot utilise des identifiants numériques (`chat_id`, `topic_id`).

---

## Prérequis

- Un groupe Telegram en mode **topics** (forum / supergroupe)
- Un topic dédié (ex. **Comida**)
- Python + `.env` configuré (voir [guide.md](guide.md))

---

## 1. Créer le bot

1. Ouvrir [@BotFather](https://t.me/BotFather)
2. `/newbot` → choisir un nom et un username (ex. `@JeanThimBot`)
3. Copier le **token** API
4. Ajouter dans `.env` :

```env
TELEGRAM_BOT_TOKEN=123456789:ABCdef...
```

> **Sécurité :** ne jamais committer le token. Si exposé (chat, screenshot), régénérer via BotFather → `/mybots` → *API Token* → **Revoke**.

---

## 2. Désactiver le Group Privacy

Par défaut, un bot **ne voit pas** les messages du groupe (sauf commandes `/…` et mentions `@Bot`).

1. [@BotFather](https://t.me/BotFather) → `/mybots`
2. Sélectionner le bot → **Bot Settings** → **Group Privacy** → **Turn off**

Vérification possible via l’API : `can_read_all_group_messages` doit être `true` (le script `telegram-setup` le confirme indirectement quand des messages arrivent).

---

## 3. Ajouter le bot au groupe

1. Groupe **Betty's coloc** (ou votre coloc) → *Ajouter des membres*
2. Chercher le bot (ex. `@JeanThimBot`)
3. Vérifier dans les membres : *has access to messages*

**Important :** les messages envoyés **avant** l’ajout du bot ou **avant** la désactivation du privacy **ne sont pas rejoués**. Il faut générer un **nouvel** événement Telegram.

---

## 4. Récupérer `chat_id` et `topic_id`

### Méthode automatique (recommandée)

```bash
# 1. Retirer puis ré-ajouter le bot au groupe (si rien n’apparaît)
# 2. Dans le topic Comida (PAS General), envoyer :
@JeanThimBot test

# 3. Sur le Mac :
uv run python validate.py telegram-setup
```

Exemple de sortie réussie (session Betty's coloc, sept. 2026) :

```
  1. Betty's coloc — General (pas de topic)
     TELEGRAM_CHAT_ID=-1004398228419

  2. Betty's coloc — topic id=2
     TELEGRAM_CHAT_ID=-1004398228419
     TELEGRAM_TOPIC_ID=2
     message : « @JeanThimBot test »
```

→ Prendre la ligne **avec un topic id** (celle du topic Comida), pas *General*.

Ajouter dans `.env` :

```env
TELEGRAM_CHAT_ID=-1004398228419
TELEGRAM_TOPIC_ID=2
```

### Méthode manuelle (plan B)

Si `telegram-setup` ne voit toujours rien :

| Id | Comment l’obtenir |
|----|-------------------|
| `TELEGRAM_CHAT_ID` | Ajouter [@getidsbot](https://t.me/getidsbot) au groupe → il affiche l’id |
| `TELEGRAM_TOPIC_ID` | Transférer un message **du topic Comida** à [@RawDataBot](https://t.me/RawDataBot) → chercher `message_thread_id` dans le JSON |

---

## 5. Tester

```bash
uv run python validate.py telegram-test
```

Un message `✅ Comida connecté…` doit apparaître **dans le topic Comida** (pas dans General).

Envoi d’un export :

```bash
uv run python validate.py send exports/promos-s1.txt
```

---

## 6. Utilisation au quotidien

```bash
# Export promo Migros + envoi Telegram
uv run python main.py promos --list S1 --telegram
```

Options `.env` :

```env
TELEGRAM_AUTO_SEND=true      # envoi auto après chaque promos
TELEGRAM_SEND_ON_PUSH=true   # résumé panier + lien checkout après push
```

---

## Dépannage

### `telegram-setup` n’affiche aucun message

| Cause | Solution |
|-------|----------|
| Privacy encore activée | BotFather → Group Privacy → **Turn off** |
| Messages trop anciens | Retirer le bot, le ré-ajouter, renvoyer `@Bot test` dans **Comida** |
| Message dans **General** | Renvoyer dans le topic **Comida** (sinon pas de `topic_id`) |
| Token incorrect | Vérifier `TELEGRAM_BOT_TOKEN` dans `.env` |

### Le bot rejoint mais `getUpdates` reste vide

1. Retirer le bot du groupe
2. Le ré-ajouter
3. Mentionner `@Bot` dans le topic Comida
4. Relancer `telegram-setup` **immédiatement**

### Message de test dans General au lieu de Comida

`TELEGRAM_TOPIC_ID` est absent ou incorrect. Seul un message envoyé **dans le topic** fournit le bon `message_thread_id`.

### Erreur `TELEGRAM_CHAT_ID manquant`

Compléter `.env` puis relancer `telegram-test`.

### Le token a fuité

BotFather → `/mybots` → **Revoke** → mettre le nouveau token dans `.env`.

---

## Référence technique

| Concept Telegram | Variable Comida |
|------------------|-----------------|
| Id du supergroupe | `TELEGRAM_CHAT_ID` (ex. `-1004398228419`) |
| Id du topic forum | `TELEGRAM_TOPIC_ID` (= `message_thread_id`, ex. `2`) |
| Topic General | Pas de `message_thread_id` → ne pas utiliser pour Comida |

Commandes utiles :

| Commande | Rôle |
|----------|------|
| `validate.py telegram-setup` | Découvrir chat_id / topic_id |
| `validate.py telegram-test` | Message de test dans le topic |
| `validate.py send <fichier>` | Envoyer un export manuellement |
| `main.py promos … --telegram` | Export promo + envoi |

Code : `src/comida/telegram.py`

---

## Checklist rapide (nouveau bot ou nouveau groupe)

- [ ] Bot créé via BotFather, token dans `.env`
- [ ] Group Privacy **désactivée**
- [ ] Bot membre du groupe coloc
- [ ] Message `@Bot test` dans le topic **Comida**
- [ ] `validate.py telegram-setup` → ids copiés dans `.env`
- [ ] `validate.py telegram-test` → message visible dans Comida
- [ ] `main.py promos --list S1 --telegram` → liste reçue sur le téléphone
