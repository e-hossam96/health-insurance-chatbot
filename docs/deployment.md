# Deployment

The demo runs as one Docker Compose stack on a single VM, served at https://health-insurance-chatbot.hossammostafa.ai with a Let's Encrypt certificate.

## 1. The VM

- **Size:** 4 vCPU, 8 GB RAM, 50 GB SSD (for example Hetzner CPX31, or AWS t3.xlarge). Docling's PDF parsing needs a few GB while a document is ingested, next to Postgres, Qdrant, Prometheus and Grafana. 2 vCPU with 8 GB works for light demos, but ingestion is slow.
- **OS:** a current Ubuntu LTS with Docker Engine and the Compose plugin.
- **Firewall:** allow 22 (SSH), 80 and 443 only. Grafana (3000) and Prometheus (9090) listen on 127.0.0.1 and are reached through an SSH tunnel; Postgres and Qdrant are not published in production, and Qdrant is reachable only on the internal Docker network.

## 2. DNS

Create an `A` record (and `AAAA` if the VM has IPv6) for `health-insurance-chatbot.hossammostafa.ai` pointing at the VM. Wait until `dig +short health-insurance-chatbot.hossammostafa.ai` returns the VM's address; Let's Encrypt checks it over HTTP.

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
| `DOMAIN` | `health-insurance-chatbot.hossammostafa.ai` |
| `LETSENCRYPT_EMAIL` | the address for certificate expiry notices |
| `LANGFUSE_*` | optional, enables tracing |

## 4. Certificate and start

```bash
bash scripts/issue_certificate.sh
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

The script starts nginx with a temporary self-signed certificate, asks Let's Encrypt for the real one over the HTTP challenge, and reloads nginx. Afterwards the `certbot` service renews it every 12 hours and nginx reloads every 6 hours to pick up a renewed certificate. Plain HTTP redirects to HTTPS, and responses carry HSTS.

## 5. First admin, demo data and documents

```bash
P="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
$P exec backend sh -c 'python scripts/create_admin.py --database-url "$DATABASE_URL" --username admin1 --password <password> --name "Admin One" --location Cairo'
$P exec backend sh -c 'python scripts/seed.py --database-url "$DATABASE_URL"'
```

Log in as the admin, open **KB documents** and upload the policy documents. The seed's sample members (`user1`, `user2`) have demo passwords; change or remove them before sharing the link widely.

## 6. Operate

- **Dashboards:** `ssh -L 3000:127.0.0.1:3000 <vm>`, then http://localhost:3000 (user `admin`, `GRAFANA_ADMIN_PASSWORD`).
- **Logs:** `$P logs -f backend`.
- **Update:** `git pull && $P up -d --build`. The backend runs database migrations on start.
- **Change the database password later:** `$P exec postgres psql -U chatbot -c "ALTER USER chatbot PASSWORD '<new>'"`, update `POSTGRES_PASSWORD` in `.env`, then `$P up -d`.
- **Backups:** `$P exec postgres pg_dump -U chatbot chatbot | gzip > backup-$(date +%F).sql.gz`, plus the `kb_data` volume (uploaded originals). Qdrant can be rebuilt by re-indexing every document from the admin page.
- **Restart:** every service has `restart: unless-stopped`, so the stack comes back after a reboot.
