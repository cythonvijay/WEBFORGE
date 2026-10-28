# Browser QA scripts

Real-browser checks used for Phase 5.5 (headless Chromium via puppeteer-core, axe-core for accessibility). Not part of `npm test`; they need a running stack and extra dev-only packages that are NOT in `frontend/package.json`.

    cd frontend/qa && npm init -y && npm i puppeteer-core @sparticuz/chromium axe-core && mkdir -p shots
    # or point lib.mjs at a local Chrome: executablePath: "/path/to/chrome"
    # start PostgreSQL, migrated backend (:8000) and `npm run dev` (:5173) / `npm run preview` (:4173), then:
    BASE=http://127.0.0.1:5173 TAG=dev node flow.mjs          # auth, session, storage/cookies, project flow, lifecycle, intake 503
    BASE=http://127.0.0.1:5173 TAG=run node responsive.mjs    # 4 viewports: overflow + screenshots, axe on 7 contexts
    BASE=http://127.0.0.1:5173 node measure.mjs               # overflow measured inside <main> (the page scrolls there)
    BASE=http://127.0.0.1:5173 node keyboard.mjs              # tab order, focus rings, dialog trap/escape/focus return, sidebar Escape
    BASE=http://127.0.0.1:4173 node net.mjs                   # request counts on the production build (no StrictMode doubles)
    BASE=http://127.0.0.1:5173 node actions.mjs               # rename/archive/restore/delete, loading, backend-down + retry (kills/restarts the backend via a stack script you provide)
    BASE=http://127.0.0.1:5173 node shots.mjs                 # screenshots in realistic project states

`actions.mjs` calls `/tmp/qa/stack.sh` to restart the backend; adjust for your machine. Findings are in docs/BUILD_PROGRESS.md.

Phase 8 scripts (they expect `qa_backend.py` — a QA-only deterministic AI test double — serving the API on :8000, and read/write `/tmp/qa/provider_mode`, one of `ok|unconfigured|error|malformed`):

    cd backend && DATABASE_URL=… JWT_SECRET=… python ../frontend/qa/qa_backend.py
    BASE=http://127.0.0.1:5173 node discovery_e2e.mjs   # idea -> discovery -> failures/retry -> answers -> reload -> round 2 -> review -> correct -> complete; DB checks need psql
    BASE=http://127.0.0.1:4173 node discovery_qa.mjs    # axe on every discovery state, overflow at 4 viewports, keyboard, per-load request counts (use the production build)

Phase 9 scripts (same QA-only `qa_backend.py` test double and `/tmp/qa/provider_mode` switch):

    BASE=http://127.0.0.1:5173 node research_e2e.mjs   # empty state, 503/502 + retry, generate, cite an examined source, submit, approve, copy-on-write edit, history, other user; DB checks need psql
    BASE=http://127.0.0.1:4173 node research_qa.mjs    # axe on 9 states, overflow at 4 viewports with 160-char unbroken text, keyboard + dialog trap, request counts (production build)
    BASE=http://127.0.0.1:4173 node research_kb.mjs    # keyboard reachability from inside the page content
