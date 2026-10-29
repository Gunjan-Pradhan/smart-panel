# Local fallback image for the Smart Load Protection Panel database.
#
# WHY THIS FILE EXISTS
#   Docker Hub's blob CDN (production.cloudfront.docker.com) is blocked by the
#   current network, so the official image timescale/timescaledb:2.31.0-pg17
#   cannot be pulled. This build uses:
#     - AWS ECR Public's mirror of the official PostgreSQL image
#     - the official TimescaleDB apt repository (packagecloud.io)
#   Both were reachable and verified on 2026-10-28.
#
# WHEN TO REMOVE IT
#   Once Docker Hub is reachable, switch docker-compose.yml back to the pinned
#   official image and delete this directory. Do not silently keep this
#   workaround forever; the official image is the preferred deployment path.
#
# VERIFIED
#   PostgreSQL 17.11, TimescaleDB 2.31.0, shared_preload_libraries=timescaledb,
#   hypertable creation and data persistence across restarts.

FROM public.ecr.aws/docker/library/postgres:17.11-bookworm

# Exact Debian package built for PostgreSQL 17 on Debian 12 (bookworm).
ARG TIMESCALEDB_PACKAGE_VERSION=2.31.0~debian12-1711

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
 && install -d /usr/share/keyrings \
 && curl -fsSL https://packagecloud.io/timescale/timescaledb/gpgkey \
      | gpg --dearmor -o /usr/share/keyrings/timescaledb.gpg \
 && echo "deb [signed-by=/usr/share/keyrings/timescaledb.gpg] https://packagecloud.io/timescale/timescaledb/debian/ bookworm main" \
      > /etc/apt/sources.list.d/timescaledb.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
      "timescaledb-2-postgresql-17=${TIMESCALEDB_PACKAGE_VERSION}" \
 && rm -rf /var/lib/apt/lists/*

# The extension must be preloaded before the server starts. The official
# postgres entrypoint copies postgresql.conf.sample into a new data directory.
RUN sed -ri "s/^#?shared_preload_libraries.*/shared_preload_libraries = 'timescaledb'/" \
      /usr/share/postgresql/postgresql.conf.sample \
 && printf "CREATE EXTENSION IF NOT EXISTS timescaledb;\n" \
      > /docker-entrypoint-initdb.d/000_timescaledb.sql

USER postgres
