import { statusClassNames } from "../constants";
import { formatStatusLabel } from "./candidate/CandidateUI";

export function StatusBadge({ status }) {
  return (
    <span className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset ${statusClassNames[status] || statusClassNames.Saved}`}>
      {formatStatusLabel(status)}
    </span>
  );
}
