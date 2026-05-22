# AI Resume Analyzer
Small full-stack app 
You paste a job description, drop in one or more resumes (PDF / DOCX / TXT), and it ranks the candidates with section-wise scores and short feedback for each one.


## Setup
You'll need Python 3.11+, Node 20+, and a Google AI Studio API key.
Get a key here: https://aistudio.google.com/apikey(Free tier for testing purpose)

### Backend
Commands - 
cd folder_location
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# open .env and paste your GEMINI_API_KEY
uvicorn app.main:app --reload --port 8000

Swagger UI is at http://127.0.0.1:8000/docs.

### Frontend

Commands - 
cd folder_location
cd frontend
npm install
npm run dev

### Try it out
1. Open the app, register an account (any email + password of 6+ chars).
2. Paste in the contents of `samples/job_description.txt`.
3. Drop the two sample resumes from `samples/` into the upload box.
4. Click Analyze. The form clears after each run so you can immediately
   start a new analysis with a different JD and a different set of resumes.


## Auth
Email + password with a JWT bearer token, kept simple on purpose.

- `POST /auth/register` and `POST /auth/login` both return `{access_token, user}`.
- The frontend stores the token in `localStorage` and sends it as
  `Authorization: Bearer <token>` on every protected call.
- Jobs and resumes are scoped per user, so two accounts on the same backend
  can't see each other's data.
- Tokens are signed with HS256 using `JWT_SECRET` from `.env`. Default
  expiry is 12 hours (`JWT_EXPIRES_MINUTES=720`).

If you want to start fresh, delete `backend/data/app.db` and restart the
backend, then register again.



## Assumptions

A few things I assumed while building this:

- Resumes are in English. Other languages might still parse but the LLM extraction was only tested on English.
- The resume has reasonably standard sections (Skills, Experience, Education, Projects). If a resume is one big paragraph with no headings the structure-based chunker still works (the LLM handles it) but quality drops.
- Section weights for the final score are 0.50 / 0.35 / 0.15 (skills / experience / education). I picked these by feel after looking at a few outputs, they live in `scorer.py` if you want to tune them.
- Long resumes are cut to 30 KB before being sent to the LLM. Anything past that is silently dropped.

## Limitations

Stuff I ran into while putting this together:

- Google AI Studio free tier on `gemini-2.5-flash-lite` is roughly 20 LLM calls per day. That is enough to demo with two or three resumes but not enough for heavy testing. 
- `text-embedding-004` was the default embedding model I started with but it returned 404 mid-project, looks like Google disabled it. Switched to `gemini-embedding-001` which works.
- `gemini-2.0-flash` returned `limit: 0` on the free tier for my key, so I moved the LLM model to `gemini-2.5-flash-lite`. 
- ChromaDB locks the collection dimensionality on first write. If you change the embedding model later you have to wipe `backend/data/chroma/` or you will get dimension-mismatch errors on insert.
- The google-generativeai SDK is inconsistent. Embedding model names need a `models/` prefix, generative model names don't. The code already handles this but it caught me out the first time.
- Scanned image-only PDFs are not OCR'd, only selectable-text PDFs or DOCX work.
- Vite 8 needs Node 20 or 22. If you are on an older Node you'll see a `CustomEvent is not defined` error on `npm run dev` and you need to upgrade Node.
