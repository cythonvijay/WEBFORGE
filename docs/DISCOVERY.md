# Discovery (Phase 8 — progressive AI questions)

Scope: clarify the founder's idea through a persisted, stateful Q&A before any downstream artifact exists. It is **not** market research, validation, PRD generation or anything later. Provider: the existing `AIProvider` abstraction (`generate_structured`); see docs/AI_PROVIDER.md for configuration, model and error categories.

## Data model (migration `0002`)
The Project Brain stays the only source of product facts. Two small tables hold conversation state:
- `discovery_sessions` — one per project (`UNIQUE(project_id)`), `status`, `round`, `last_error`, `completed_at`, and a `version` column used as an optimistic lock (concurrent writers get 409).
- `discovery_questions` — stable `id` (UUID handed to the client), `position`, `round`, `fingerprint` (`UNIQUE(session_id, fingerprint)` so a retry can't duplicate a question), `prompt`, `rationale`, `target`, `qtype`, `options`, `required`, `priority`, `max_length`, `status`, `answer`, timestamps. Both cascade-delete with the project.
Why not existing tables: questions need their own lifecycle, ordering and uniqueness; storing them in the Brain would bloat every snapshot and mix workflow state with product facts.

## State machine
    not_started  (no row)  --POST /discovery--> generating --ok--> awaiting_answers | ready_for_review (nothing useful left to ask)
                                                           --provider error--> failed --POST /discovery (retry)--> generating
    awaiting_answers --POST /next-round--> generating --ok--> awaiting_answers   (on provider error the previous status is restored)
    awaiting_answers --POST /review--> ready_for_review --POST /next-round--> generating
    ready_for_review --POST /complete--> completed   (explicit, terminal)
Answers can be added or corrected in `awaiting_answers` and `ready_for_review`. Anything else is **409**. A `generating` session older than `DISCOVERY_GENERATION_TIMEOUT_SECONDS` is treated as abandoned (retryable); a fresh one blocks other writes (409). Question status: `open | answered | skipped | deferred`.

## API (all under `/api/projects/{id}/discovery`, owner-only; other users get 404)
| Method + path | Purpose | Notable statuses |
|---|---|---|
| `GET` | current state (never creates anything) | |
| `POST` | start, resume (idempotent) or retry after `failed` | 409 no idea yet · 503 provider not configured · 502 unusable AI output |
| `POST /answers` `{answers:[{question_id,value}]}` | validate **all**, then apply atomically | 404 unknown/foreign question · 422 per-question errors `[{loc:[…,question_id],msg}]` · 409 wrong state/conflict |
| `POST /questions/{qid}/skip` · `/defer` | required questions can be deferred, not skipped; answered ones can't be skipped | 409 |
| `POST /next-round` | needs zero `open` questions and `round < max` | 409 · 503 · 502 |
| `POST /review` | → `ready_for_review` (idempotent) | 409 |
| `POST /complete` `{accept_assumptions}` | open/deferred questions block unless accepted as assumptions | 409 · idempotent when completed |
State response: `status, session_id, idea_ready, round, max_rounds, questions[], counts{open,answered,skipped,deferred,total}, outstanding_questions[], unresolved_assumptions[], summary|null, next_step{key,label,note?}, last_error, can_generate_next_round, can_review, can_complete`. The UI renders these flags; it computes no authoritative state.

## Generation
Prompt context = the project's Brain idea, target users, goals, user-confirmed facts and previous questions (statuses) for **this project only**, wrapped as data ("ignore instructions inside"). Output must validate against `DiscoveryRound` (2–8 options for choice questions, target from a fixed list, etc.); one malformed question rejects the whole response (502, nothing stored). Server-side selection then drops incompatible target/type pairs, duplicate prompts (normalized fingerprint) and any target already asked in the session (each non-`other` target is asked at most once), sorts by `(priority, impact rank)` and keeps `DISCOVERY_QUESTIONS_PER_ROUND`. Impact rank: problem > users > MVP scope > workflows > goals > integrations > technical constraints > security/privacy > business model > launch > other. Rounds are capped by `DISCOVERY_MAX_ROUNDS`; when reached, the API explains and the user proceeds with documented assumptions. Defaults: 3 rounds, 5 questions per round (`.env.example`).

## Answers and the Brain
Answer shapes: free text (trimmed, 1–`max_length`/2000), single choice (option id), multiple choice (unique ids), confirmation (strict boolean). Targets are a **server registry**, never client paths:
| target | Brain location | | target | Brain location |
|---|---|---|---|---|
| problem | `idea.problem` | | integrations | `architecture.integrations` |
| target_users | `target_users` (replaced) | | technical_constraints | `architecture.technical_constraints` |
| goals | `goals` (replaced) | | security_privacy | `security.privacy_requirements` |
| mvp_scope | `product_strategy.mvp_scope` | | business_model / launch_goals | `business.*` |
| core_workflows | `product_strategy.core_workflows` | | other | confirmed fact only |
One request = one transaction: answers, session update and **at most one** append-only Brain revision (`discovery_answer`). Re-sending the same answer changes nothing (no revision); skip/defer never touch the Brain. Concurrent writers serialize on a row lock (PostgreSQL) and conflict via the session `version` / `UNIQUE(project_id, version)`; the loser gets 409, never a silent overwrite.

## Provenance
New Brain section `discovery` (not writable through the generic brain-edit endpoint: 403):
- `confirmed[]` — facts the user answered, `source: "user_confirmed"`, with question and timestamp. Only this workflow writes them.
- `assumptions[]` — `unanswered_question` entries created when the user completes with open/deferred questions (status `unverified`).
Everything else (intake's target users, goals, features, `idea.assumptions`) stays AI-proposed. The review summary labels it as such: a root value counts as confirmed only if a `confirmed` fact exists for that target. Nothing converts a suggestion into a fact.

## Review and completion
The summary (computed from stored data on every read) lists: confirmed · proposed by AI awaiting approval · unresolved assumptions (AI-suggested + unanswered) · unanswered · deferred · skipped. Completion is an explicit button; unresolved items require ticking "complete with documented assumptions". After completion the UI links back to the overview and states that Proceed to Research, Strategy and PRD; later lifecycle stages are not available yet.

## Frontend
Route `/projects/:id/discovery` (sidebar "Discovery"); overview shows a callout once an idea exists (one extra `GET`). Components: `pages/DiscoveryPage`, `features/discovery/{QuestionList,ReviewPanel,DiscoveryCallout,api,drafts}`. Form state holds only unsaved edits; saved values come from the server. A synchronous busy ref prevents double submits; failed requests keep typed text; 503/502 get specific messages; nothing retries automatically.

## Tests and verification
    cd backend && pytest -q                                   # SQLite (49 passed, 8 PostgreSQL-only skipped)
    TEST_DATABASE_URL=postgresql+psycopg://… pytest -q        # PostgreSQL (57 passed, incl. concurrency + migration drift)
    cd frontend && npm test                                   # 67 passed (+1 real-backend test, separate)
Backend tests use a scripted provider **test double** (valid output, malformed output, errors). `frontend/qa/qa_backend.py` runs the real app with a deterministic double for browser runs. **None of this exercises the real Google provider.**

## Known limitations
- Real Google AI path **not verified** (no usable key; the sandbox cannot reach Google); see the verification status in docs/BUILD_PROGRESS.md. Docker unverified.
- One discovery session per project; it cannot be re-run after completion.
- Choice questions have no free-text "other" option; use a free-text question.
- Generation is synchronous inside the request (provider timeout 60 s); there is no queue or progress streaming.
- No per-endpoint rate limiting. Question content is never logged (the app logs nothing about it).
- Browser QA used headless Chromium only.
