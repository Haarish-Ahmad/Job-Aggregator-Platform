import { useId, useRef, useState, type ChangeEvent } from "react";
import { Icon } from "./Icon";

export const RESUME_ACCEPT = ".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document";
const RESUME_EXTENSIONS = [".pdf", ".docx"];
const RESUME_MAX_BYTES = 5 * 1024 * 1024;

/** Why a picked resume can't be used, or undefined if it's fine. Browsers often report DOCX with an empty type, so the extension decides. */
export function resumeProblem(file: File): string | undefined {
  const name = file.name.toLowerCase();
  if (!RESUME_EXTENSIONS.some((ext) => name.endsWith(ext))) return "Choose a PDF or DOCX file.";
  if (file.size === 0) return "That file is empty.";
  if (file.size > RESUME_MAX_BYTES) return "That file is larger than 5 MB.";
  return undefined;
}

export function fileSize(bytes: number): string {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Resume picker for the profile. The file only lives in React state: nothing is uploaded or saved. */
export function ResumeUpload({ file, onChange }: { file: File | null; onChange: (file: File | null) => void }) {
  const id = useId();
  const input = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string>();
  const choose = () => input.current?.click();

  function pick(e: ChangeEvent<HTMLInputElement>) {
    const chosen = e.target.files?.[0];
    e.target.value = ""; // so the same file can be picked again
    if (!chosen) return; // dialog cancelled
    const problem = resumeProblem(chosen);
    setError(problem);
    if (!problem) onChange(chosen); // an invalid replacement keeps the current file
  }
  function remove() {
    setError(undefined);
    onChange(null);
  }

  return (
    <div className="resume-upload">
      <label htmlFor={id}>Resume</label>
      <input id={id} ref={input} type="file" accept={RESUME_ACCEPT} onChange={pick} hidden />
      {file ? (
        <div className="resume-box has-file">
          <Icon name="file" size={22} />
          <span className="resume-meta">
            <strong>{file.name}</strong>
            <small>{fileSize(file.size)}</small>
          </span>
          <span className="resume-actions">
            <button type="button" className="btn small" onClick={choose} aria-label={`Replace ${file.name}`}>Replace</button>
            <button type="button" className="btn small ghost" onClick={remove} aria-label={`Remove ${file.name}`}>Remove</button>
          </span>
        </div>
      ) : (
        <div className="resume-box">
          <span className="resume-icon"><Icon name="upload" size={22} /></span>
          <strong>Upload your resume</strong>
          <small>PDF or DOCX, up to 5 MB</small>
          <button type="button" className="btn small" onClick={choose}>Choose file</button>
        </div>
      )}
      {file && <p className="resume-note">Not saved yet: this file stays in this tab only and is lost if you refresh or leave the page.</p>}
      {error && <p className="form-error" role="alert">{error}</p>}
    </div>
  );
}
