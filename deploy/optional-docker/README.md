# Docker (optional)

This project does not require Docker — see the main README.md for the
native (venv + systemd) setup, which is the default deployment path.

If you'd rather use Docker anyway, these files are kept here for
convenience:

```bash
cp ../../.env.example ../../.env   # fill it in first
cd ../..
docker build -f deploy/optional-docker/Dockerfile -t bcommie .
docker run --env-file .env --restart unless-stopped -d bcommie
```

Or with Compose (only starts the bot process; MongoDB Atlas and Neon are
external services, not containers):

```bash
docker compose -f deploy/optional-docker/docker-compose.yml up -d --build
```
