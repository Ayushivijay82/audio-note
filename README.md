# Audio Notes

Upload an audio file of any length and get back a transcript (Gnani ASR) and a summary (Gemini).
Past uploads are listed and can be reopened. How it works: see the app's `/architecture` page.

**Live app:** https://audio-notes-chi.vercel.app (architecture: https://audio-notes-chi.vercel.app/architecture)
**API:** https://api-production-20a22.up.railway.app/health

```
frontend/   Next.js 16 (App Router, Tailwind) - deployed on Vercel
backend/    FastAPI API + background worker - deployed on Railway (one Docker image, two services)
            app/main.py     HTTP API (upload, status, retry)
            app/worker.py   job loop: download -> ffprobe -> ffmpeg chunks -> Gnani -> Gemini
            app/gnani.py    Gnani STT client with retries
            app/audio.py    ffprobe / ffmpeg helpers
            app/llm.py      Gemini summary
            app/storage.py  Supabase Storage (S3 API) presigned URLs
            app/models.py   recordings + chunks tables (the recordings table is also the job queue)
```

## Run locally

You need Python 3.12+, Node.js 20+, ffmpeg, and Postgres (via Docker/Podman, or any hosted Postgres URL).

### Linux / macOS

```bash
# Postgres
docker run -d --name notes-pg -e POSTGRES_USER=notes -e POSTGRES_PASSWORD=notes \
  -e POSTGRES_DB=notes -p 5432:5432 postgres:17

# Backend (two terminals)
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env            # then fill in the keys
.venv/bin/uvicorn app.main:app --reload   # terminal 1: API on :8000
.venv/bin/python -m app.worker            # terminal 2: worker

# Frontend
cd frontend
cp .env.example .env.local
npm install && npm run dev                # http://localhost:3000
```

### Windows (PowerShell)

```powershell
# One-time installs
winget install Python.Python.3.12
winget install OpenJS.NodeJS.LTS
winget install Gyan.FFmpeg            # restart the terminal afterwards so ffmpeg is on PATH
# Postgres: install Docker Desktop and run the same `docker run ... postgres:17` command as above,
# or skip it and put a hosted Postgres URL (e.g. Railway's) in DATABASE_URL.

# Backend (two terminals)
cd backend
py -3.12 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env                # then fill in the keys
.venv\Scripts\uvicorn app.main:app --reload     # terminal 1
.venv\Scripts\python -m app.worker              # terminal 2

# Frontend
cd frontend
copy .env.example .env.local
npm install
npm run dev
```

Quick Gnani check without the rest of the stack:
`python -m scripts.try_gnani path\to\clip.mp3 en-IN` (sends the first 25 s).

## Deploy

**Railway (backend)**: create a project from this GitHub repo.
1. Add a **Postgres** database.
2. Service **api**: root directory `backend`, uses the Dockerfile. Variables: `DATABASE_URL=${{Postgres.DATABASE_URL}}`,
   `GNANI_API_KEY`, `GEMINI_API_KEY`, `S3_ENDPOINT_URL`, `S3_REGION`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_BUCKET`,
   `FRONTEND_ORIGIN=https://<your-app>.vercel.app`. Generate a public domain.
3. Service **worker**: same repo, root `backend`, same variables plus `SERVICE_ROLE=worker`, no public domain.

**Vercel (frontend)**: import the repo, root directory `frontend`, set `NEXT_PUBLIC_API_URL=https://<api>.up.railway.app`
and `NEXT_PUBLIC_GITHUB_URL`.

**Storage**: Supabase project -> Storage -> create a private bucket `audio-notes`; Storage -> S3 Configuration ->
enable the S3 connection and create an access key. Supabase allows browser uploads from any origin, so no CORS setup.
(On Cloudflare R2 / AWS S3 instead, run `python -m scripts.setup_cors` once.)
