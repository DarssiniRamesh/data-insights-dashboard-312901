# Project Repository

## Backend (manual local development)

A convenience script is provided to install backend dependencies and run the backend locally (without the preview system).

```bash
cd data-insights-dashboard-312901/backend_api
chmod +x run_local_backend.sh
./run_local_backend.sh
```

Defaults:
- HOST=127.0.0.1
- PORT=8000

Useful endpoints once running:
- http://127.0.0.1:8000/docs (Swagger UI)
- http://127.0.0.1:8000/health (liveness)
- http://127.0.0.1:8000/ready (readiness)

Optional environment variables:
- `HOST`, `PORT`, `LOG_LEVEL`