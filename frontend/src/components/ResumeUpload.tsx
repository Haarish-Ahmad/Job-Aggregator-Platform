import { useId, useRef, useState, type ChangeEvent } from "react";
import { Icon } from "./Icon";
import type { ResumeParseResult } from "../lib/types";

export const RESUME_ACCEPT = ".pdf,application/pdf";
const RESUME_EXTENSIONS = [".pdf"];
const RESUME_MAX_BYTES = 10_000_000;

export function resumeProblem(file: File): string | undefined {
  const name = file.name.toLowerCase();
  if (!RESUME_EXTENSIONS.some((ext) => name.endsWith(ext))) return "Choose a PDF file.";
  if (file.size === 0) return "That file is empty.";
  if (file.size > RESUME_MAX_BYTES) return "That file is larger than 10 MB.";
  return undefined;
}

export function fileSize(bytes: number): string {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function ResumeUpload({
  hasResume,
  onUpload,
  onDownload,
}: {
  hasResume: boolean;
  onUpload: (file: File) => Promise<ResumeParseResult>;
  onDownload: () => Promise<void>;
}) {
  const id = useId();
  const input = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string>();
  const [message, setMessage] = useState<string>();
  const [file, setFile] = useState<File | null>(null);
  const [parsed, setParsed] = useState<ResumeParseResult>();
  const [busy, setBusy] = useState(false);
  const choose = () => input.current?.click();

  async function pick(e: ChangeEvent<HTMLInputElement>) {
    const chosen = e.target.files?.[0];
    e.target.value = "";
    if (!chosen) return;
    const problem = resumeProblem(chosen);
    setError(problem);
    setMessage(undefined);
    setParsed(undefined);
    if (problem) return;
    setFile(chosen);
    setBusy(true);
    try {
      const result = await onUpload(chosen);
      setParsed(result);
      setMessage("Resume uploaded and parsed. Review the extracted details, then save your profile.");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function download() {
    setError(undefined);
    try {
      await onDownload();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <div className="resume-upload">
      <label htmlFor={id}>Resume</label>
      <input id={id} ref={input} type="file" accept={RESUME_ACCEPT} onChange={(e) => void pick(e)} hidden />
      {file ? (
        <div className="resume-box has-file">
          <Icon name="file" size={22} />
          <span className="resume-meta">
            <strong>{file.name}</strong>
            <small>{fileSize(file.size)}</small>
          </span>
          <button type="button" className="btn small" onClick={choose} disabled={busy}>Replace</button>
        </div>
      ) : (
        <div className="resume-box">
          <span className="resume-icon"><Icon name="upload" size={22} /></span>
          <strong>{hasResume ? "Your resume is saved" : "Upload your resume"}</strong>
          <small>Text-based PDF, up to 10 MB</small>
          <button type="button" className="btn small" onClick={choose} disabled={busy}>{busy ? "Uploading…" : "Choose PDF"}</button>
        </div>
      )}
      {hasResume && <button type="button" className="link" onClick={() => void download()}>Download saved resume</button>}
      {busy && <p role="status">Uploading and extracting resume details…</p>}
      {message && <p className="form-ok" role="status">{message}</p>}
      {parsed && (
        <div className="resume-results">
          <strong>Extracted from resume</strong>
          <p>Skills: {parsed.skills.length ? parsed.skills.join(", ") : "None detected"}</p>
          <p>CGPA: {parsed.cgpa ?? "Not detected"} · Graduation year: {parsed.grad_year ?? "Not detected"}</p>
        </div>
      )}
      {error && <p className="form-error" role="alert">{error}</p>}
    </div>
  );
}
