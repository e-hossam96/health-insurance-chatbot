#!/usr/bin/env bash
set -euo pipefail

COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.prod.yml)

read_env() {
    grep -E "^$1=" .env | tail -1 | cut -d= -f2- | tr -d '"\r'
}

DOMAIN="$(read_env DOMAIN)"
LETSENCRYPT_EMAIL="$(read_env LETSENCRYPT_EMAIL)"
: "${DOMAIN:?set DOMAIN in .env}"
: "${LETSENCRYPT_EMAIL:?set LETSENCRYPT_EMAIL in .env}"
LIVE="/etc/letsencrypt/live/${DOMAIN}"
MARKER="/etc/letsencrypt/.temporary-${DOMAIN}"

temporary_certificate() {
    "${COMPOSE[@]}" run --rm --entrypoint sh certbot -c "apk add --no-cache openssl >/dev/null && mkdir -p ${LIVE} \
        && openssl req -x509 -nodes -newkey rsa:2048 -days 1 -subj /CN=${DOMAIN} -keyout ${LIVE}/privkey.pem -out ${LIVE}/fullchain.pem \
        && touch ${MARKER}"
}

if "${COMPOSE[@]}" run --rm --entrypoint sh certbot -c "test -f ${LIVE}/fullchain.pem && test ! -f ${MARKER}"; then
    echo "A certificate for ${DOMAIN} already exists; the certbot service renews it."
    exit 0
fi

echo "Creating a temporary self-signed certificate so nginx can start..."
temporary_certificate
"${COMPOSE[@]}" up -d --build frontend

echo "Requesting the Let's Encrypt certificate for ${DOMAIN}..."
"${COMPOSE[@]}" run --rm --entrypoint sh certbot -c "rm -rf ${LIVE} /etc/letsencrypt/archive/${DOMAIN} /etc/letsencrypt/renewal/${DOMAIN}.conf ${MARKER}"
if ! "${COMPOSE[@]}" run --rm --entrypoint certbot certbot certonly --webroot -w /var/www/certbot \
    -d "${DOMAIN}" --email "${LETSENCRYPT_EMAIL}" --agree-tos --no-eff-email --non-interactive; then
    echo "Let's Encrypt refused the request; restoring the temporary certificate so nginx keeps running." >&2
    echo "Check that the DNS record points at this machine and port 80 is open, then run this script again." >&2
    temporary_certificate
    "${COMPOSE[@]}" exec frontend nginx -s reload
    exit 1
fi

"${COMPOSE[@]}" exec frontend nginx -s reload
echo "Done: https://${DOMAIN}"
