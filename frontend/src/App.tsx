import { useEffect, useRef, useState } from "react";
import { api, auth, AnalyzeResponse, AuthUser } from "./api";
import { Auth } from "./pages/Auth";
import { ResultsTable } from "./components/ResultsTable";
import { ResultDetail } from "./components/ResultDetail";

const MAX_FILES = 10;

export default function App() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [bootstrapping, setBootstrapping] = useState(true);

  const [jobTitle, setJobTitle] = useState("");
  const [jobDesc, setJobDesc] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [results, setResults] = useState<AnalyzeResponse | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Try to restore the session on first paint.
  useEffect(() => {
    const t = auth.getToken();
    if (!t) { setBootstrapping(false); return; }
    api.me()
      .then(setUser)
      .catch(() => { auth.clear(); })
      .finally(() => setBootstrapping(false));
  }, []);

  if (bootstrapping) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-sky-50 via-blue-50 to-indigo-50">
        <div className="text-slate-400 text-sm">Loading…</div>
      </div>
    );
  }

  if (!user) {
    return <Auth onLoggedIn={setUser} />;
  }

  function logout() {
    auth.clear();
    setUser(null);
    setResults(null);
    setJobTitle("");
    setJobDesc("");
    setFiles([]);
  }

  function resetForm() {
    setJobTitle("");
    setJobDesc("");
    setFiles([]);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  function handlePick(e: React.ChangeEvent<HTMLInputElement>) {
    const picked = Array.from(e.target.files ?? []);
    // Reset the input so picking the SAME file again later still fires onChange.
    e.target.value = "";
    if (picked.length === 0) return;

    // Merge picked files into the existing list, deduped by name + size.
    const seen = new Set(files.map((f) => `${f.name}|${f.size}`));
    const merged = [...files];
    let droppedDup = 0;
    for (const f of picked) {
      const key = `${f.name}|${f.size}`;
      if (seen.has(key)) { droppedDup++; continue; }
      seen.add(key);
      merged.push(f);
    }

    let next = merged;
    let droppedCap = 0;
    if (next.length > MAX_FILES) {
      droppedCap = next.length - MAX_FILES;
      next = next.slice(0, MAX_FILES);
    }
    setFiles(next);

    if (droppedCap > 0) {
      setError(`Max ${MAX_FILES} files allowed. ${droppedCap} file(s) ignored.`);
    } else if (droppedDup > 0) {
      setError(`${droppedDup} duplicate file(s) skipped.`);
    } else {
      setError(null);
    }
  }

  function removeFile(idx: number) {
    setFiles((prev) => prev.filter((_, i) => i !== idx));
    setError(null);
  }

  function clearFiles() {
    setFiles([]);
    if (fileInputRef.current) fileInputRef.current.value = "";
    setError(null);
  }

  async function runFullFlow() {
    setError(null);
    try {
      if (!jobTitle.trim() || !jobDesc.trim()) {
        setError("Please provide a job title and description.");
        return;
      }
      if (files.length === 0) {
        setError("Please upload at least one resume.");
        return;
      }

      setBusy("Creating job…");
      const createdJob = await api.createJob(jobTitle, jobDesc);

      setBusy(`Uploading ${files.length} resume(s)…`);
      const uploaded = await api.uploadResumes(files);

      setBusy("Analyzing…");
      const res = await api.analyze(createdJob.id, uploaded.map((r) => r.id));
      setResults(res);
      setSelected(res.ranked[0]?.resume_id ?? null);

      // Clear the form so the next JD/resume cycle starts fresh.
      resetForm();
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setBusy(null);
    }
  }

  const selectedItem = results?.ranked.find((r) => r.resume_id === selected) ?? null;

  return (
    <div className="min-h-screen bg-gradient-to-br from-sky-50 via-blue-50 to-indigo-50 text-slate-900">
      <header className="bg-white/70 backdrop-blur border-b border-blue-100">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-blue-500 to-blue-700 text-white flex items-center justify-center font-bold">
              R
            </div>
            <div>
              <h1 className="text-lg font-semibold">AI Resume Analyzer</h1>
              <p className="text-xs text-slate-500">
                Structure-aware chunking · Gemini · ChromaDB RAG · reranker
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-slate-500 hidden sm:inline">
              {user.email}
            </span>
            <a
              className="text-sm text-blue-600 hover:underline"
              href="http://127.0.0.1:8000/docs"
              target="_blank"
              rel="noreferrer"
            >
              API docs
            </a>
            <button
              onClick={logout}
              className="text-sm text-slate-600 hover:text-slate-900 border border-slate-300 rounded-md px-3 py-1"
            >
              Logout
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-6 grid grid-cols-1 lg:grid-cols-3 gap-6">
        <section className="lg:col-span-1 bg-white rounded-2xl border border-blue-100 shadow-sm p-5 space-y-4">
          <div>
            <h2 className="font-semibold text-slate-900">1. Job Description</h2>
            <p className="text-xs text-slate-500">
              Paste the JD you want to match against.
            </p>
          </div>
          <input
            className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            placeholder="Job title (e.g. Senior Python Engineer)"
            value={jobTitle}
            onChange={(e) => setJobTitle(e.target.value)}
          />
          <textarea
            className="w-full h-44 border border-slate-300 rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            placeholder="Paste full job description here…"
            value={jobDesc}
            onChange={(e) => setJobDesc(e.target.value)}
          />

          <div>
            <h2 className="font-semibold text-slate-900 pt-2">
              2. Upload Resumes
            </h2>
            <p className="text-xs text-slate-500">
              PDF, DOCX, or TXT. Up to {MAX_FILES} files. Pick more files to
              append to the list — duplicates are skipped.
            </p>
          </div>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".pdf,.docx,.txt"
            onChange={handlePick}
            disabled={files.length >= MAX_FILES}
            className="block w-full text-sm text-slate-700 file:mr-3 file:py-2 file:px-3 file:rounded-lg file:border-0 file:text-sm file:font-medium file:bg-blue-100 file:text-blue-700 hover:file:bg-blue-200 disabled:opacity-50"
          />

          {files.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <p className="text-xs text-slate-500">
                  {files.length} of {MAX_FILES} selected
                </p>
                <button
                  type="button"
                  onClick={clearFiles}
                  className="text-xs text-slate-500 hover:text-red-600"
                >
                  Clear all
                </button>
              </div>
              <ul className="space-y-1.5 max-h-56 overflow-y-auto pr-1">
                {files.map((f, i) => (
                  <li
                    key={`${f.name}|${f.size}|${i}`}
                    className="flex items-center gap-2 text-xs bg-blue-50 border border-blue-100 rounded-md px-2.5 py-1.5"
                  >
                    <span className="flex-1 truncate text-slate-800" title={f.name}>
                      {f.name}
                    </span>
                    <span className="text-slate-500 shrink-0">
                      {f.size < 1024
                        ? `${f.size} B`
                        : `${(f.size / 1024).toFixed(0)} KB`}
                    </span>
                    <button
                      type="button"
                      onClick={() => removeFile(i)}
                      className="text-slate-400 hover:text-red-600 ml-1 px-1"
                      aria-label={`Remove ${f.name}`}
                      title="Remove"
                    >
                      ✕
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <button
            className="w-full bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-700 hover:to-blue-800 disabled:from-slate-300 disabled:to-slate-300 disabled:text-slate-500 text-white rounded-lg py-2.5 text-sm font-medium shadow-sm transition-all"
            onClick={runFullFlow}
            disabled={!!busy}
          >
            {busy || "Analyze"}
          </button>

          {error && (
            <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg p-3">
              {error}
            </div>
          )}
        </section>

        <section className="lg:col-span-2 space-y-6">
          {results ? (
            <>
              <div className="bg-white rounded-2xl border border-blue-100 shadow-sm p-5">
                <div className="flex items-center justify-between mb-3">
                  <h2 className="font-semibold text-slate-900">
                    Ranked Candidates
                  </h2>
                  <span className="text-xs text-slate-500">
                    {results.job_title}
                  </span>
                </div>
                <ResultsTable
                  items={results.ranked}
                  selectedId={selected}
                  onSelect={setSelected}
                />
              </div>
              {selectedItem && <ResultDetail item={selectedItem} />}
            </>
          ) : (
            <div className="bg-white rounded-2xl border border-blue-100 shadow-sm p-10 text-center text-slate-500">
              <div className="inline-flex w-12 h-12 rounded-full bg-blue-50 text-blue-600 items-center justify-center mb-3 font-semibold">
                ↑
              </div>
              <p className="text-sm">
                Add a job description, upload one or more resumes,
                then click <span className="font-medium text-slate-700">Analyze</span>.
              </p>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
