import { AnalyzeItem } from "../api";

export function ResultsTable({
  items,
  selectedId,
  onSelect,
}: {
  items: AnalyzeItem[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="text-left text-slate-500 border-b border-slate-200">
          <tr>
            <th className="py-2 pr-3">#</th>
            <th className="py-2 pr-3">Candidate</th>
            <th className="py-2 pr-3">File</th>
            <th className="py-2 pr-3 text-right">Skills</th>
            <th className="py-2 pr-3 text-right">Experience</th>
            <th className="py-2 pr-3 text-right">Education</th>
            <th className="py-2 pr-3 text-right">Total</th>
          </tr>
        </thead>
        <tbody>
          {items.map((it, i) => {
            const selected = it.resume_id === selectedId;
            return (
              <tr
                key={it.resume_id}
                onClick={() => onSelect(it.resume_id)}
                className={
                  "cursor-pointer border-b border-blue-50 hover:bg-blue-50/60 transition-colors " +
                  (selected ? "bg-blue-50" : "")
                }
              >
                <td className="py-2 pr-3 font-medium">{i + 1}</td>
                <td className="py-2 pr-3">
                  <div className="font-medium">{it.name || "(unknown)"}</div>
                  <div className="text-xs text-slate-500">{it.email || ""}</div>
                </td>
                <td className="py-2 pr-3 text-xs text-slate-600">{it.filename}</td>
                <td className="py-2 pr-3 text-right tabular-nums">{it.skills_score.toFixed(1)}</td>
                <td className="py-2 pr-3 text-right tabular-nums">{it.experience_score.toFixed(1)}</td>
                <td className="py-2 pr-3 text-right tabular-nums">{it.education_score.toFixed(1)}</td>
                <td className="py-2 pr-3 text-right">
                  <span
                    className={
                      "inline-block rounded-md px-2 py-0.5 text-xs font-semibold " +
                      scoreColor(it.total_score)
                    }
                  >
                    {it.total_score.toFixed(1)}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function scoreColor(score: number): string {
  if (score >= 75) return "bg-green-100 text-green-800";
  if (score >= 55) return "bg-amber-100 text-amber-800";
  return "bg-red-100 text-red-800";
}
