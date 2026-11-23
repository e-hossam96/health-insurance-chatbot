# Deployment

The demo runs as one Docker Compose stack on a single VM, served at https://health-insurance-chatbot-demo.hossammostafa.ai. Caddy terminates HTTPS and gets its Let's Encrypt certificate on its own.

## 1. The VM

- **Size:** 4 vCPU, 8 GB RAM, 50 GB SSD (for example Hetzner CPX31, or AWS t3.xlarge). Docling's PDF parsing needs a few GB while a document is ingested, next to Postgres, Qdrant, Prometheus and Grafana. 2 vCPU with 8 GB works for light demos, but ingestion is slow.
- **OS:** a current Ubuntu LTS with Docker Engine and the Compose plugin.
- **Firewall:** allow 22 (SSH), 80 and 443 (TCP, plus UDP 443 for HTTP/3) only. Grafana (3000) and Prometheus (9090) listen on 127.0.0.1 and are reached through an SSH tunnel; Postgres and Qdrant are not published in production, and Qdrant is reachable only on the internal Docker network.

## 2. DNS

Create an `A` record (and `AAAA` if the VM has IPv6) for `health-insurance-chatbot-demo.hossammostafa.ai` pointing at the VM. Wait until `dig +short health-insurance-chatbot-demo.hossammostafa.ai` returns the VM's address; Let's Encrypt checks it over HTTP.

## 3. Configure

```bash
git clone <repo> health-insurance-chatbot && cd health-insurance-chatbot
cp .env.example .env
```

Fill in `.env`:

| Variable | Value |
|---|---|
| `OPENAI_API_KEY` | the API key |
| `AI_*_MODEL`, `AI_*_REASONING_EFFORT`, `AI_EMBEDDING_DIMENSIONS` | as in `.env.example` |
| `GRAFANA_ADMIN_PASSWORD` | a long random password |
| `POSTGRES_PASSWORD` | letters and digits only, for example `openssl rand -hex 24`. Set it before the first start: Postgres stores it when the volume is created |
| `DOMAIN` | `health-insurance-chatbot-demo.hossammostafa.ai`. The link-preview tags in `frontend/index.html` hold this domain as absolute URLs, so change them too if it changes |
| `LETSENCRYPT_EMAIL` | the address for certificate expiry notices |
| `LANGFUSE_*` | optional, enables tracing |

## 4. Start

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

On its first start Caddy asks Let's Encrypt for the certificate of `DOMAIN` (DNS must already point at the VM and ports 80 and 443 must be open), keeps it in the `caddy_data` volume and renews it on its own. Plain HTTP redirects to HTTPS, responses carry HSTS, and HTTP/3 is served on 443/udp. Watch the first issue with `docker logs -f health-chatbot-caddy`.

Caddy is the only published service. It reaches the frontend nginx on the `edge` network from the fixed address 172.31.250.250, the one address nginx trusts for `X-Forwarded-For` (rate limits per client, F15). Postgres and Qdrant sit on the `data` network, which has no route to the internet in production.

**Moving from the certbot setup.** Networks changed, so recreate the stack once: `docker compose -f docker-compose.yml -f docker-compose.prod.yml down` (without `-v`, which would delete the data), then the `up -d --build` command above. The old `certbot_conf` and `certbot_www` volumes are no longer used; remove them with `docker volume rm` when the new certificate works.

## 5. First admin, demo data and documents

```bash
P="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
$P exec backend python scripts/create_admin.py --username admin1 --password <password> --name "Admin One" --location Cairo
$P exec backend python scripts/seed.py
```

Log in as the admin, open **KB documents** and upload the knowledge-base documents (policy handbook, member guide and similar) that answer members' insurance questions. The seed's sample members (`user1`, `user2`) have demo passwords; change or remove them before sharing the link widely.

## 6. Operate

- **Dashboards:** `ssh -L 3000:127.0.0.1:3000 <vm>`, then http://localhost:3000 (user `admin`, `GRAFANA_ADMIN_PASSWORD`).
- **Logs:** `$P logs -f backend`.
- **Update:** `git pull && $P up -d --build`. The backend runs database migrations on start.
- **Change the database password later:** `$P exec postgres psql -U chatbot -c "ALTER USER chatbot PASSWORD '<new>'"`, update `POSTGRES_PASSWORD` in `.env`, then `$P up -d`.
- **Backups:** `$P exec postgres pg_dump -U chatbot chatbot | gzip > backup-$(date +%F).sql.gz`, plus the `kb_data` volume (uploaded originals). Qdrant can be rebuilt by re-indexing every document from the admin page.
- **Restart:** every service has `restart: unless-stopped`, so the stack comes back after a reboot.
