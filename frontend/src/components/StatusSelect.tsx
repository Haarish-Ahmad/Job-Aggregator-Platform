import { STATUS_LABELS } from "../lib/format";
import { APPLICATION_STATUSES, type ApplicationStatus } from "../lib/types";

/** Application status picker, coloured like the matching badge. Any status can be picked at any time. */
export function StatusSelect({ value, onChange, disabled, label }: { value: ApplicationStatus; onChange: (status: ApplicationStatus) => void; disabled?: boolean; label: string }) {
  return (
    <select className={`status-select status-${value}`} value={value} disabled={disabled} aria-label={label} onChange={(e) => onChange(e.target.value as ApplicationStatus)}>
      {APPLICATION_STATUSES.map((s) => (
        <option key={s} value={s}>
          {STATUS_LABELS[s]}
        </option>
      ))}
    </select>
  );
}
