# magma-cycling-tools

Ops tooling et adapters pour [magma-cycling](https://github.com/stephanejouve/magma-cycling).

Repo sidecar séparé du core `magma-cycling` et distinct de `outillages`
(cross-project Talk / github-utils / moderation). Contient les outils
spécifiques au workflow training-logs / Zwift / cyclisme.

## Structure

```
magma_cycling_tools/
├── ops/        # data_repo_sync, future provision-writer, migrate-training-logs
└── adapters/   # futur : implémentations concrètes des interfaces magma-cycling
                #         (ex. scrapers whatsonzwift → WorkoutCatalog)
```

Dépendance unidirectionnelle : `magma-cycling-tools` → `magma-cycling`
(interfaces). Jamais l'inverse.

## Tools inclus

### `data-repo-sync`

Auto-commit + pull-rebase + push dans le repo de training data. Tourne via
cron (supercronic) dans le container magma-cycling à 22h30 quotidien +
20h30 dimanche.

```bash
poetry run data-repo-sync             # Commit + push si changements
poetry run data-repo-sync --dry-run   # Aperçu sans rien écrire
```

Variables d'env : `TRAINING_DATA_REPO` ou `TRAINING_LOGS_PATH`
(chemin absolu vers le checkout du repo de données).

Alerting Talk best-effort (room `infra-alerts`) sur échec
fetch/rebase/push. Guardé par `ImportError` : si `outillages.nextcloud_talk`
n'est pas installé (cas container minimal), l'échec reste loggué mais
l'alerte est silencieusement skippée.

## Dev

```bash
poetry install
poetry run pre-commit install
poetry run pytest
```

## Consommation

### Depuis magma-cycling (Docker)

`docker/Dockerfile` du repo `magma-cycling` tire ce package via :

```dockerfile
RUN --mount=type=secret,id=gh_token \
    pip install git+https://$(cat /run/secrets/gh_token)@github.com/stephanejouve/magma-cycling-tools.git@main
```

### Depuis le Mac (dev)

```bash
poetry run pip install -e ~/Projects/magma-cycling-tools
```

## Licence

MIT.
