import { AnalyzeItem } from "../api";

export function ResultDetail({ item }: { item: AnalyzeItem }) {
  return (
    <div className="bg-white rounded-2xl border border-blue-100 shadow-sm p-5 space-y-5">
      <header>
        <h2 className="font-semibold text-lg">
          {item.name || item.filename}
        </h2>
        <p className="text-xs text-slate-500">{item.email}</p>
      </header>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <ScorePill label="Total" value={item.total_score} highlight />
        <ScorePill label="Skills" value={item.skills_score} />
        <ScorePill label="Experience" value={item.experience_score} />
        <ScorePill label="Education" value={item.education_score} />
      </div>

      <SkillsBlock matched={item.matched_skills} missing={item.missing_skills} />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <FeedbackList title="Strengths" items={item.feedback.strengths} tone="green" />
        <FeedbackList title="Improvements" items={item.feedback.improvements} tone="amber" />
      </div>
    </div>
  );
}

function ScorePill({ label, value, highlight }: { label: string; value: number; highlight?: boolean }) {
  return (
    <div className={"rounded-lg border p-3 " + (highlight ? "border-blue-200 bg-blue-50" : "border-slate-200")}>
      <div className="text-xs text-slate-500">{label}</div>
      <div className="text-xl font-semibold tabular-nums">{value.toFixed(1)}</div>
    </div>
  );
}

function SkillsBlock({ matched, missing }: { matched: string[]; missing: string[] }) {
  return (
    <div className="space-y-3">
      <div>
        <div className="text-xs font-medium text-slate-500 mb-1">Matched skills</div>
        <div className="flex flex-wrap gap-1.5">
          {matched.length === 0 && <span className="text-xs text-slate-400">(none)</span>}
          {matched.map((s) => (
            <span key={s} className="text-xs bg-green-50 text-green-800 border border-green-200 rounded-md px-2 py-0.5">
              {s}
            </span>
          ))}
        </div>
      </div>
      <div>
        <div className="text-xs font-medium text-slate-500 mb-1">Missing skills</div>
        <div className="flex flex-wrap gap-1.5">
          {missing.length === 0 && <span className="text-xs text-slate-400">(none)</span>}
          {missing.map((s) => (
            <span key={s} className="text-xs bg-red-50 text-red-800 border border-red-200 rounded-md px-2 py-0.5">
              {s}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

function FeedbackList({ title, items, tone }: { title: string; items: string[]; tone: "green" | "amber" }) {
  const colors =
    tone === "green"
      ? "border-green-200 bg-green-50/40"
      : "border-amber-200 bg-amber-50/40";
  return (
    <div className={"rounded-lg border p-4 " + colors}>
      <h3 className="text-sm font-semibold mb-2">{title}</h3>
      {items.length === 0 ? (
        <p className="text-xs text-slate-500">No feedback generated.</p>
      ) : (
        <ul className="list-disc list-inside text-sm space-y-1">
          {items.map((s, i) => (
            <li key={i}>{s}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
