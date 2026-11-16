#!/usr/bin/env bash
set -euo pipefail

COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)
set -a
. ./.env
set +a
: "${DOMAIN:?set DOMAIN in .env}"
: "${LETSENCRYPT_EMAIL:?set LETSENCRYPT_EMAIL in .env}"
LIVE="/etc/letsencrypt/live/${DOMAIN}"

if "${COMPOSE[@]}" run --rm --entrypoint sh certbot -c "test -f ${LIVE}/fullchain.pem && ! grep -q 'temporary' /etc/letsencrypt/.temporary-${DOMAIN} 2>/dev/null"; then
    echo "A certificate for ${DOMAIN} already exists; certbot renews it automatically."
    exit 0
fi

echo "Creating a temporary self-signed certificate so nginx can start..."
"${COMPOSE[@]}" run --rm --entrypoint sh certbot -c "apk add --no-cache openssl >/dev/null && mkdir -p ${LIVE} && openssl req -x509 -nodes -newkey rsa:2048 -days 1 -subj /CN=${DOMAIN} -keyout ${LIVE}/privkey.pem -out ${LIVE}/fullchain.pem && echo temporary > /etc/letsencrypt/.temporary-${DOMAIN}"

echo "Starting the stack..."
"${COMPOSE[@]}" up -d --build frontend

echo "Requesting the Let's Encrypt certificate for ${DOMAIN}..."
"${COMPOSE[@]}" run --rm --entrypoint sh certbot -c "rm -rf ${LIVE} /etc/letsencrypt/archive/${DOMAIN} /etc/letsencrypt/renewal/${DOMAIN}.conf /etc/letsencrypt/.temporary-${DOMAIN}"
"${COMPOSE[@]}" run --rm --entrypoint certbot certbot certonly --webroot -w /var/www/certbot \
    -d "${DOMAIN}" --email "${LETSENCRYPT_EMAIL}" --agree-tos --no-eff-email --non-interactive

echo "Reloading nginx with the real certificate..."
"${COMPOSE[@]}" exec frontend nginx -s reload
echo "Done: https://${DOMAIN}"
