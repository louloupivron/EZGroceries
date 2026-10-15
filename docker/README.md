# Comida sur Docker (optionnel — NAS ou serveur)

> Sur le serveur maison, mets à jour avec `scripts/update.sh` plutôt que `git pull`. Voir « Serveur (Docker) » dans le [README](../README.md).

UI Comida accessible 24/7 depuis le téléphone (même Wi‑Fi ou via Tailscale).

## Prérequis

- Docker + Docker Compose (Synology **Container Manager**, QNAP **Container Station**, etc.)
- Fichier `.env` configuré (copie de `.env.example`)

## Démarrage

```bash
docker compose up -d --build
```

Interface : **http://\<ip-nas\>:8765** (ex. `http://192.168.1.50:8765`)

## Volumes

| Chemin hôte | Rôle |
|-------------|------|
| `./data` | Session validation, cache promos, session Migros |
| `./exports` | Exports Kookd (`semaine.txt`, …) |
| `./docs` | Page mobile (`validate.py publish`) |
| `./.env` | Identifiants Migros |
| `garde-manger.txt`, `courses-hebdo.txt`, `mappings.json` | Config |

## Workflow hebdo

1. Déposer `exports/semaine.txt` (sync NAS, SFTP, ou depuis le Mac)
2. Ouvrir l’UI sur le téléphone
3. **Analyser semaine** → valider favoris → **Push Migros**

## Commandes utiles

```bash
# Logs
docker compose logs -f comida

# Lister les listes Migros (première config)
docker compose run --rm --entrypoint "" comida uv run python validate.py lists

# Régénérer la page mobile
docker compose run --rm --entrypoint "" comida uv run python validate.py publish

# Arrêt
docker compose down
```

## Accès depuis l’extérieur (optionnel)

- **Tailscale** sur le NAS : `http://100.x.x.x:8765` sans ouvrir de ports
- **Reverse proxy** Synology + HTTPS si exposition publique (non recommandé sans auth)

## Synology

1. Copier le projet dans un dossier partagé (ex. `/docker/comida`)
2. Container Manager → Projet → Coller `docker-compose.yml` ou importer le dossier
3. Vérifier que le port **8765** est autorisé dans le pare-feu DSM
