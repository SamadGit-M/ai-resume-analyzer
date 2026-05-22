const BASE = "/api";
const TOKEN_KEY = "ara_token";

export type Job = {
  id: number;
  title: string;
  description: string;
  structured?: any;
  created_at: string;
};

export type Resume = {
  id: number;
  filename: string;
  name?: string | null;
  email?: string | null;
  structured?: any;
  created_at: string;
};

export type AnalyzeItem = {
  resume_id: number;
  filename: string;
  name: string | null;
  email: string | null;
  total_score: number;
  skills_score: number;
  experience_score: number;
  education_score: number;
  matched_skills: string[];
  missing_skills: string[];
  feedback: { strengths: string[]; improvements: string[] };
};

export type AnalyzeResponse = {
  job_id: number;
  job_title: string;
  ranked: AnalyzeItem[];
};

export type AuthUser = { id: number; email: string; created_at: string };
export type AuthResp = { access_token: string; token_type: string; user: AuthUser };

export const auth = {
  getToken(): string | null {
    return localStorage.getItem(TOKEN_KEY);
  },
  setToken(t: string) {
    localStorage.setItem(TOKEN_KEY, t);
  },
  clear() {
    localStorage.removeItem(TOKEN_KEY);
  },
};

function headers(extra?: Record<string, string>): Record<string, string> {
  const h: Record<string, string> = { ...(extra || {}) };
  const t = auth.getToken();
  if (t) h["Authorization"] = `Bearer ${t}`;
  return h;
}

async function handle<T>(res: Response): Promise<T> {
  if (res.status === 401) {
    auth.clear();
    throw new Error("Session expired. Please log in again.");
  }
  if (!res.ok) {
    let detail = await res.text();
    try {
      const j = JSON.parse(detail);
      detail = j.detail || detail;
    } catch {
      // not JSON, keep as is
    }
    throw new Error(`${res.status}: ${detail}`);
  }
  return res.json();
}

export const api = {
  async register(email: string, password: string): Promise<AuthResp> {
    return handle<AuthResp>(
      await fetch(`${BASE}/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      })
    );
  },

  async login(email: string, password: string): Promise<AuthResp> {
    return handle<AuthResp>(
      await fetch(`${BASE}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      })
    );
  },

  async me(): Promise<AuthUser> {
    return handle<AuthUser>(
      await fetch(`${BASE}/auth/me`, { headers: headers() })
    );
  },

  async createJob(title: string, description: string): Promise<Job> {
    return handle<Job>(
      await fetch(`${BASE}/jobs`, {
        method: "POST",
        headers: headers({ "Content-Type": "application/json" }),
        body: JSON.stringify({ title, description }),
      })
    );
  },

  async listJobs(): Promise<Job[]> {
    return handle<Job[]>(await fetch(`${BASE}/jobs`, { headers: headers() }));
  },

  async uploadResumes(files: File[]): Promise<Resume[]> {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    return handle<Resume[]>(
      await fetch(`${BASE}/resumes/upload`, {
        method: "POST",
        body: fd,
        headers: headers(),
      })
    );
  },

  async listResumes(): Promise<Resume[]> {
    return handle<Resume[]>(
      await fetch(`${BASE}/resumes`, { headers: headers() })
    );
  },

  async analyze(job_id: number, resume_ids?: number[]): Promise<AnalyzeResponse> {
    return handle<AnalyzeResponse>(
      await fetch(`${BASE}/analyze`, {
        method: "POST",
        headers: headers({ "Content-Type": "application/json" }),
        body: JSON.stringify({ job_id, resume_ids: resume_ids ?? null }),
      })
    );
  },
};
