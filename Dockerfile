# Étape de construction : uv installe les dépendances figées par uv.lock.
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Les dépendances sont installées avant le code source : cette couche n'est
# reconstruite que si uv.lock change, pas à chaque modification d'un module.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app ./app


# Étape finale : ni uv ni chaîne de compilation, seulement l'environnement
# résolu (psycopg[binary] embarque déjà libpq, voir pyproject.toml).
FROM python:3.14-slim-bookworm AS runtime

RUN groupadd --system enervision \
    && useradd --system --gid enervision --create-home enervision

WORKDIR /app

COPY --from=builder --chown=enervision:enervision /app/.venv /app/.venv
COPY --from=builder --chown=enervision:enervision /app/app ./app

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Sans utilisateur dédié, un processus compromis s'exécuterait en root dans le
# conteneur.
USER enervision

EXPOSE 3000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3000"]
