"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { ApiError, BrandContext, ChatResponse, Comment, displayTime, request, uploadVideo, Video } from "@/lib/api";
import { CommentComposer } from "@/components/CommentComposer";
import { CommentFilter, FeedbackPanel, FeedbackTab } from "@/components/FeedbackPanel";
import { ReviewPlayer, ReviewPlayerHandle } from "@/components/ReviewPlayer";

const FIRST_PASS_REQUEST = "Review the full video and add timestamped comments at the most important moments.";

export default function Home() {
  const [video, setVideo] = useState<Video | null>(null);
  const [context, setContext] = useState<BrandContext>("NONE");
  const [file, setFile] = useState<File | null>(null);
  const [showUpload, setShowUpload] = useState(false);
  const [busy, setBusy] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [currentMs, setCurrentMs] = useState(0);
  const [mediaReady, setMediaReady] = useState(false);
  const [commentAt, setCommentAt] = useState<number | null>(null);
  const [draft, setDraft] = useState("");
  const [commentError, setCommentError] = useState("");
  const [savingComment, setSavingComment] = useState(false);
  const [removingCommentId, setRemovingCommentId] = useState<string | null>(null);
  const [removeError, setRemoveError] = useState("");
  const [retryingPreparation, setRetryingPreparation] = useState(false);
  const [preparationError, setPreparationError] = useState("");
  const [chatDraft, setChatDraft] = useState("");
  const [chatError, setChatError] = useState("");
  const [reviewError, setReviewError] = useState("");
  const [chatBusy, setChatBusy] = useState(false);
  const [requestKind, setRequestKind] = useState<"REVIEW" | "CHAT" | null>(null);
  const [tab, setTab] = useState<FeedbackTab>("COMMENTS");
  const [filter, setFilter] = useState<CommentFilter>("ALL");
  const [selectedCommentId, setSelectedCommentId] = useState<string | null>(null);
  const [newComments, setNewComments] = useState<Comment[]>([]);
  const player = useRef<ReviewPlayerHandle>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const activeVideoId = useRef<string | null>(null);
  const chatRequestId = useRef(0);

  function activate(saved: Video | null) {
    activeVideoId.current = saved?.id ?? null;
    chatRequestId.current += 1;
    setVideo(saved);
    setContext(saved?.brand_context ?? "NONE");
    setCurrentMs(0); setMediaReady(false); setCommentAt(null); setDraft(""); setCommentError(""); setRemovingCommentId(null); setRemoveError("");
    setPreparationError(""); setChatDraft(""); setChatError(""); setReviewError(""); setChatBusy(false); setRequestKind(null);
    setTab("COMMENTS"); setFilter("ALL"); setSelectedCommentId(null); setNewComments([]);
    setShowUpload(false);
  }

  useEffect(() => {
    let cancelled = false;
    async function restore() {
      const id = new URLSearchParams(window.location.search).get("video");
      setLoading(true); setError("");
      try {
        const saved = id ? await request<Video>(`/api/videos/${encodeURIComponent(id)}`) : null;
        if (!cancelled) activate(saved);
      } catch (err) {
        if (!cancelled) { activate(null); setError((err as Error).message); }
      } finally { if (!cancelled) setLoading(false); }
    }
    void restore();
    window.addEventListener("popstate", restore);
    return () => { cancelled = true; window.removeEventListener("popstate", restore); };
  }, []);

  useEffect(() => {
    if (!video || video.ai_status !== "PROCESSING") return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const videoId = video.id;
    async function poll() {
      try {
        const saved = await request<Video>(`/api/videos/${encodeURIComponent(videoId)}`);
        if (cancelled) return;
        setPreparationError("");
        setVideo(current => current?.id === videoId ? { ...current, ai_status: saved.ai_status, ai_error: saved.ai_error } : current);
        if (saved.ai_status === "PROCESSING") timer = setTimeout(poll, 2000);
      } catch (err) {
        if (cancelled) return;
        setPreparationError(`${(err as Error).message} Retrying…`);
        timer = setTimeout(poll, 2000);
      }
    }
    timer = setTimeout(poll, 2000);
    return () => { cancelled = true; if (timer) clearTimeout(timer); };
  }, [video?.id, video?.ai_status]);

  async function upload(event: FormEvent) {
    event.preventDefault();
    if (!file || busy) return;
    setError("");
    if (file.size > 100 * 1024 * 1024) { setError("The video must be 100 MiB or smaller."); return; }
    setBusy(true); setUploadProgress(0);
    const body = new FormData(); body.append("file", file); body.append("brand_context", context);
    try {
      const saved = await uploadVideo(body, setUploadProgress);
      activate(saved);
      window.history.pushState({}, "", `/?video=${saved.id}`);
      setFile(null);
      if (fileInput.current) fileInput.current.value = "";
    } catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }

  function playerTime(): number { return Math.min(Math.max(player.current?.getCurrentTimeMs() ?? currentMs, 0), video?.duration_ms ?? 0); }
  function changeCommentDraft(text: string) {
    if (!draft && text && commentAt === null) setCommentAt(playerTime());
    setDraft(text); setCommentError("");
  }

  function selectComment(comment: Comment) {
    setTab("COMMENTS");
    setFilter(current => current === "ALL" || current === comment.author ? current : comment.author);
    setSelectedCommentId(comment.id);
    player.current?.seekTo(comment.timestamp_ms);
  }

  async function saveComment(event: FormEvent) {
    event.preventDefault();
    if (!video || savingComment) return;
    const text = draft.trim(); const timestampMs = commentAt ?? playerTime();
    setCommentError("");
    if (!text) { setCommentError("Write a comment before saving."); return; }
    if (text.length > 1000) { setCommentError("Comments can contain at most 1,000 characters."); return; }
    setSavingComment(true);
    try {
      const saved = await request<Comment>(`/api/videos/${video.id}/comments`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ timestamp_ms: timestampMs, text }) });
      setVideo(current => current?.id === saved.video_id ? { ...current, comments: [...current.comments, saved].sort((a, b) => a.timestamp_ms - b.timestamp_ms || a.created_at.localeCompare(b.created_at)) } : current);
      setDraft(""); setCommentAt(null); setTab("COMMENTS"); setFilter("HUMAN"); setSelectedCommentId(saved.id);
    } catch (err) { setCommentError((err as Error).message); }
    finally { setSavingComment(false); }
  }

  async function removeComment(comment: Comment) {
    if (!video || removingCommentId || !window.confirm("Remove this comment?")) return;
    setRemovingCommentId(comment.id); setRemoveError("");
    try {
      await request<void>(`/api/videos/${video.id}/comments/${comment.id}`, { method: "DELETE" });
      setVideo(current => current?.id === video.id ? { ...current, comments: current.comments.filter(item => item.id !== comment.id) } : current);
      setNewComments(current => current.filter(item => item.id !== comment.id));
      setSelectedCommentId(current => current === comment.id ? null : current);
    } catch (err) { setRemoveError((err as Error).message); }
    finally { setRemovingCommentId(null); }
  }

  async function retryPreparation() {
    if (!video || retryingPreparation) return;
    setRetryingPreparation(true); setPreparationError("");
    try {
      const saved = await request<Video>(`/api/videos/${video.id}/prepare`, { method: "POST" });
      setVideo(current => current?.id === saved.id ? { ...current, ai_status: saved.ai_status, ai_error: saved.ai_error } : current);
    } catch (err) { setPreparationError((err as Error).message); }
    finally { setRetryingPreparation(false); }
  }

  async function sendChat(message: string, clearDraft: boolean) {
    if (!video || video.ai_status !== "READY" || chatBusy) return;
    const text = message.trim();
    if (!text) { setChatError("Write a message before sending."); return; }
    if (text.length > 4000) { setChatError("Messages can contain at most 4,000 characters."); return; }
    const videoId = video.id;
    const fullReview = !clearDraft && text === FIRST_PASS_REQUEST;
    const requestId = ++chatRequestId.current;
    setTab(fullReview ? "COMMENTS" : "CHAT"); setChatBusy(true); setRequestKind(fullReview ? "REVIEW" : "CHAT"); setChatError(""); setReviewError("");
    try {
      const saved = await request<ChatResponse>(`/api/videos/${videoId}/chat`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message: text }) });
      if (activeVideoId.current !== videoId || chatRequestId.current !== requestId) return;
      setVideo(current => {
        if (current?.id !== videoId) return current;
        const comments = new Map(current.comments.map(comment => [comment.id, comment]));
        for (const id of saved.deleted_comment_ids) comments.delete(id);
        for (const comment of [...saved.updated_comments, ...saved.comments]) comments.set(comment.id, comment);
        return { ...current, comments: [...comments.values()].sort((a, b) => a.timestamp_ms - b.timestamp_ms || a.created_at.localeCompare(b.created_at)), messages: [...current.messages, saved.user_message, saved.assistant_message] };
      });
      if (saved.deleted_comment_ids.length) setSelectedCommentId(current => current && saved.deleted_comment_ids.includes(current) ? null : current);
      setNewComments(current => current.filter(comment => !saved.deleted_comment_ids.includes(comment.id)).map(comment => saved.updated_comments.find(updated => updated.id === comment.id) ?? comment));
      if (fullReview) { setTab("COMMENTS"); setFilter("ALL"); setSelectedCommentId(saved.comments[0]?.id ?? null); setNewComments([]); }
      else if (saved.comments.length) setNewComments(saved.comments);
      if (clearDraft) setChatDraft("");
    } catch (err) {
      if (activeVideoId.current !== videoId || chatRequestId.current !== requestId) return;
      const confirmedFailure = err instanceof ApiError && ["invalid_ai_response", "ai_response_incomplete", "ai_response_blocked"].includes(err.code ?? "");
      const message = (err as Error).message;
      try {
        const refreshed = await request<Video>(`/api/videos/${encodeURIComponent(videoId)}`);
        if (activeVideoId.current !== videoId || chatRequestId.current !== requestId) return;
        setVideo(current => current?.id === videoId ? refreshed : current);
        const notice = confirmedFailure ? message : `${message} Check the saved conversation before retrying; the request may have completed.`;
        if (fullReview) setReviewError(notice); else setChatError(notice);
      } catch {
        if (activeVideoId.current !== videoId || chatRequestId.current !== requestId) return;
        const notice = confirmedFailure ? message : `${message} We could not refresh the saved conversation. Check it before retrying.`;
        if (fullReview) setReviewError(notice); else setChatError(notice);
      }
    } finally { if (activeVideoId.current === videoId && chatRequestId.current === requestId) { setChatBusy(false); setRequestKind(null); } }
  }

  const onReadyChange = useCallback((ready: boolean) => setMediaReady(ready), []);
  const onPlaybackError = useCallback(() => setError("The video could not be played. Reload the page or try a supported MP4."), []);
  const reviewSummary = (() => {
    if (!video) return null;
    for (let index = video.messages.length - 2; index >= 0; index--) {
      const request = video.messages[index];
      const reply = video.messages[index + 1];
      if (request.role === "USER" && request.text === FIRST_PASS_REQUEST && reply.role === "ASSISTANT") return reply.text;
    }
    return null;
  })();
  const uploadForm = <form onSubmit={upload} className="upload-form">
    <label>Video file<input ref={fileInput} type="file" accept=".mp4,video/mp4" disabled={busy || loading} onChange={event => setFile(event.target.files?.[0] ?? null)} /></label>
    <label>Review context<select value={context} disabled={busy || loading} onChange={event => setContext(event.target.value as BrandContext)}><option value="NONE">General</option><option value="MRQ">MRQ</option></select></label>
    <button type="submit" disabled={!file || busy || loading}>{busy ? uploadProgress < 100 ? `Uploading ${uploadProgress}%` : "Validating video…" : "Upload video"}</button>
    {busy && <div className="upload-progress" role="progressbar" aria-label="Video upload progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={uploadProgress}><span style={{ width: `${uploadProgress}%` }} /></div>}
    {busy && <p className="upload-status" role="status">{uploadProgress < 100 ? "Sending video from your device…" : "Upload sent. Waiting for server validation…"}</p>}
    <p className="upload-note">MP4 · H.264 · AAC or silent · up to 100 MiB / 5 minutes. Existing reviews keep their saved context.</p>
  </form>;

  return <main className="app-shell">
    <header className="app-header"><div className="header-title"><span className="app-brand">FOXELLI <span>/</span> VIDEO REVIEW</span>{video ? <><h1 title={video.original_filename}>{video.original_filename}</h1><div className="header-meta"><span>{video.brand_context === "MRQ" ? "MRQ" : "General"}</span><span>·</span><span>{displayTime(video.duration_ms)}</span><span>·</span><span className={`status-text status-${video.ai_status.toLowerCase()}`}>{video.ai_status === "PROCESSING" ? "Preparing for AI review…" : video.ai_status === "READY" ? "Ready for AI review" : "AI preparation needs attention"}</span></div></> : <h1>Video review</h1>}</div><div className="header-actions">{video && <><button type="button" className="secondary-button" onClick={() => { if (!showUpload) setContext("NONE"); setShowUpload(value => !value); }}>{showUpload ? "Close upload" : "Upload another video"}</button><button type="button" className="primary-button" disabled={video.ai_status !== "READY" || chatBusy} onClick={() => void sendChat(FIRST_PASS_REQUEST, false)}>{chatBusy ? "Reviewing…" : "Review full video"}</button></>}</div></header>
    {(showUpload || !video) && !loading && <section className={`upload-drawer ${video ? "compact" : ""}`}><div><h2>{video ? "Upload another video" : "Start a review"}</h2><p>{video ? "Your current review stays open until the new upload succeeds." : "Upload a video to watch, comment, and request AI feedback."}</p></div>{uploadForm}{error && <p className="error" role="alert">{error}</p>}</section>}
    {video && video.ai_status === "FAILED" && <div className="status-alert"><span>{video.ai_error ?? "Preparation failed. Retry when ready."}</span><button type="button" disabled={retryingPreparation} onClick={retryPreparation}>{retryingPreparation ? "Retrying…" : "Retry preparation"}</button></div>}
    {preparationError && <p className="error status-inline" role="alert">{preparationError}</p>}
    {error && video && !showUpload && <p className="error status-inline" role="alert">{error}</p>}
    {loading ? <p className="loading-state" role="status">Loading your review…</p> : video ? <div className="workspace"><section className="review-column" aria-label="Video and comment composer"><ReviewPlayer ref={player} video={video} selectedCommentId={selectedCommentId} onSelectComment={selectComment} onTimeChange={setCurrentMs} onReadyChange={onReadyChange} onPlaybackError={onPlaybackError} /><CommentComposer draft={draft} timestampMs={commentAt} currentMs={currentMs} ready={mediaReady} saving={savingComment} error={commentError} onChange={changeCommentDraft} onUseCurrentTime={() => { setCommentAt(playerTime()); setCommentError(""); }} onSubmit={saveComment} /></section><FeedbackPanel video={video} reviewSummary={reviewSummary} reviewBusy={requestKind === "REVIEW"} reviewError={reviewError} tab={tab} filter={filter} selectedCommentId={selectedCommentId} chatDraft={chatDraft} chatBusy={chatBusy} chatError={chatError} newCommentsCount={newComments.length} removingCommentId={removingCommentId} removeError={removeError} onTab={setTab} onFilter={setFilter} onSelectComment={selectComment} onRemoveComment={comment => { void removeComment(comment); }} onChatDraft={setChatDraft} onSubmitChat={event => { event.preventDefault(); void sendChat(chatDraft, true); }} onViewNewComments={() => { if (newComments[0]) selectComment(newComments[0]); setFilter("AI"); setNewComments([]); }} /></div> : <div className="empty-state"><div className="empty-visual">▶</div><h2>Review the moments that matter</h2><p>Upload a video to begin.</p></div>}
  </main>;
}
