# syntax=docker/dockerfile:1
# Etapa 1 — Builder: compila el frontend con Vite
FROM node:22-alpine AS builder

ARG BUILD_COMMIT
ARG BUILD_TIMESTAMP
ARG VITE_GOOGLE_CLIENT_ID
ENV VITE_GOOGLE_CLIENT_ID=$VITE_GOOGLE_CLIENT_ID
LABEL build.commit=$BUILD_COMMIT build.timestamp=$BUILD_TIMESTAMP

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

# Etapa 2 — Final: solo runtime de Python + el build estático
FROM python:3.12-slim

ARG BUILD_COMMIT
ARG BUILD_TIMESTAMP
LABEL build.commit=$BUILD_COMMIT build.timestamp=$BUILD_TIMESTAMP

WORKDIR /app

# Dependencias del backend
COPY nodeboard-backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código del backend (app/, alembic.ini, migrations/, etc.)
COPY nodeboard-backend/ .

# Build del frontend → static/ (donde main.py lo espera)
COPY --from=builder /app/dist/ app/static/

# Directorio para volúmenes persistentes (ej. SQLite). En Railway se setea
# DATA_PATH=/data y se monta un Volume en /data para que los datos sobrevivan
# entre deploys. En desarrollo local DATA_PATH no está definida y se usa el
# default relativo (./nodeboard.db).
RUN mkdir -p /data

# Entrypoint con migraciones + arranque
COPY nodeboard-backend/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

CMD ["/app/entrypoint.sh"]
