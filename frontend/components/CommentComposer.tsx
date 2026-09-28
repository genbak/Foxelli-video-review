"use client";

import { FormEvent } from "react";
import { displayTime } from "@/lib/api";

type Props = {
  draft: string;
  timestampMs: number | null;
  currentMs: number;
  ready: boolean;
  saving: boolean;
  error: string;
  onChange: (text: string) => void;
  onUseCurrentTime: () => void;
  onSubmit: (event: FormEvent) => void;
};

export function CommentComposer({ draft, timestampMs, currentMs, ready, saving, error, onChange, onUseCurrentTime, onSubmit }: Props) {
  return <form className="comment-composer" onSubmit={onSubmit}>
    <label className="sr-only" htmlFor="human-comment">Add a timestamped comment</label>
    <textarea id="human-comment" value={draft} maxLength={1000} rows={3} disabled={!ready || saving} placeholder="Write your comment here…" onChange={event => onChange(event.target.value)} />
    <div className="comment-composer-footer">
      <div className="composer-time"><span className="attached-time" aria-label={`Comment timestamp ${displayTime(timestampMs ?? currentMs)}`}>● {displayTime(timestampMs ?? currentMs)}</span><button type="button" className="quiet-button" disabled={!ready || saving} onClick={onUseCurrentTime}>Use current time</button></div>
      <div className="composer-actions"><span className="counter">{draft.length}/1,000</span><button type="submit" disabled={!ready || saving || !draft.trim()}>{saving ? "Posting…" : "Post comment"}</button></div>
    </div>
    {timestampMs !== null && <p className="timestamp-help">Timestamp locked when you started typing.</p>}
    {error && <p className="error" role="alert">{error}</p>}
  </form>;
}
