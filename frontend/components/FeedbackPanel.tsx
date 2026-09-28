"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { Comment, displayTime, Video } from "@/lib/api";
import { MessageContent } from "./MessageContent";

export type FeedbackTab = "COMMENTS" | "CHAT";
export type CommentFilter = "ALL" | "AI" | "HUMAN";
type Props = { video: Video; reviewSummary: string | null; reviewBusy: boolean; reviewError: string; tab: FeedbackTab; filter: CommentFilter; selectedCommentId: string | null; chatDraft: string; chatBusy: boolean; chatError: string; newCommentsCount: number; removingCommentId: string | null; removeError: string; onTab: (tab: FeedbackTab) => void; onFilter: (filter: CommentFilter) => void; onSelectComment: (comment: Comment) => void; onRemoveComment: (comment: Comment) => void; onChatDraft: (text: string) => void; onSubmitChat: (event: FormEvent) => void; onViewNewComments: () => void };

export function FeedbackPanel({ video, reviewSummary, reviewBusy, reviewError, tab, filter, selectedCommentId, chatDraft, chatBusy, chatError, newCommentsCount, removingCommentId, removeError, onTab, onFilter, onSelectComment, onRemoveComment, onChatDraft, onSubmitChat, onViewNewComments }: Props) {
  const conversation = useRef<HTMLDivElement>(null);
  const nearBottom = useRef(true);
  const previousMessageCount = useRef(video.messages.length);
  const [newReply, setNewReply] = useState(false);
  const visible = video.comments.filter(comment => filter === "ALL" || comment.author === filter);
  const aiCount = video.comments.filter(comment => comment.author === "AI").length;
  const humanCount = video.comments.length - aiCount;

  useEffect(() => {
    if (tab !== "COMMENTS" || !selectedCommentId) return;
    const node = document.getElementById(`comment-${selectedCommentId}`);
    if (node) requestAnimationFrame(() => node.scrollIntoView({ block: "nearest", behavior: "smooth" }));
  }, [selectedCommentId, tab, filter, visible.length]);

  useEffect(() => {
    const increased = video.messages.length > previousMessageCount.current;
    previousMessageCount.current = video.messages.length;
    if (increased && !nearBottom.current) setNewReply(true);
    if (tab !== "CHAT") return;
    const node = conversation.current;
    if (!node) return;
    if (nearBottom.current) { node.scrollTop = node.scrollHeight; setNewReply(false); }
  }, [video.messages.length, tab]);

  return <aside className="feedback-panel" aria-label="Review feedback">
    <div className="feedback-tabs" role="tablist" aria-label="Feedback views">
      <button type="button" role="tab" aria-selected={tab === "COMMENTS"} className={tab === "COMMENTS" ? "active" : ""} onClick={() => onTab("COMMENTS")}>Comments <span>{video.comments.length}</span></button>
      <button type="button" role="tab" aria-selected={tab === "CHAT"} className={tab === "CHAT" ? "active" : ""} onClick={() => onTab("CHAT")}>AI chat</button>
    </div>
    {tab === "COMMENTS" ? <>
      {reviewBusy && <div className="review-notice" role="status">Reviewing video… Your comments remain available.</div>}
      {reviewError && <p className="error review-notice" role="alert">{reviewError}</p>}
      {reviewSummary && <div className="review-summary"><div className="review-summary-label">Latest full-review verdict · AI</div><MessageContent text={reviewSummary} /></div>}
      <div className="comment-filters" aria-label="Filter comments">
        {(["ALL", "AI", "HUMAN"] as const).map(option => <button type="button" key={option} className={filter === option ? "active" : ""} aria-pressed={filter === option} onClick={() => onFilter(option)}>{option === "ALL" ? "All" : option === "AI" ? "AI" : "Human"} <span>{option === "ALL" ? video.comments.length : option === "AI" ? aiCount : humanCount}</span></button>)}
      </div>
      {removeError && <p className="error review-notice" role="alert">{removeError}</p>}
      <div className="feedback-scroll comments-scroll">
        {visible.length ? <ol className="comment-list">{visible.map(comment => <li key={comment.id} id={`comment-${comment.id}`} className={selectedCommentId === comment.id ? "selected" : ""}>
          <div className="comment-meta">
            <span className={`author-icon ${comment.author === "AI" ? "ai" : "human"}`} aria-hidden="true">{comment.author === "AI" ? "✦" : "●"}</span>
            <span className="author-label">{comment.author === "AI" ? "AI" : "Human"}</span>
            <button type="button" className="time-button" onClick={() => onSelectComment(comment)}>{displayTime(comment.timestamp_ms)}</button>
            <button type="button" className="remove-comment-button" disabled={removingCommentId !== null} aria-label={`Remove ${comment.author === "AI" ? "AI" : "Human"} comment at ${displayTime(comment.timestamp_ms)}`} onClick={() => onRemoveComment(comment)}>{removingCommentId === comment.id ? "Removing…" : "Remove"}</button>
          </div>
          <button type="button" className="comment-body-button" onClick={() => onSelectComment(comment)}>{comment.text}</button>
        </li>)}</ol> : <div className="feedback-empty">{video.comments.length ? "No comments in this filter." : "No comments yet. Add one below the video or request an AI review."}</div>}
      </div>
    </> : <>
      <div className="conversation-wrap"><div ref={conversation} className="feedback-scroll conversation" onScroll={event => { const node = event.currentTarget; nearBottom.current = node.scrollHeight - node.scrollTop - node.clientHeight < 80; if (nearBottom.current) setNewReply(false); }} aria-live="polite">
        {video.messages.length ? video.messages.map(message => <article key={message.id} className={`message message-${message.role.toLowerCase()}`}><span className="message-author">{message.role === "USER" ? "You" : "AI assistant"}</span>{message.role === "ASSISTANT" ? <MessageContent text={message.text} /> : <p>{message.text}</p>}</article>) : <div className="feedback-empty">No conversation yet. Use Review full video or ask a focused question.</div>}
      </div></div>
      {newReply && <button type="button" className="new-reply" onClick={() => { if (conversation.current) conversation.current.scrollTop = conversation.current.scrollHeight; nearBottom.current = true; setNewReply(false); }}>New reply ↓</button>}
      {newCommentsCount > 0 && <button type="button" className="new-comments" onClick={onViewNewComments}>View {newCommentsCount} new comment{newCommentsCount === 1 ? "" : "s"} →</button>}
      <form className="chat-form" onSubmit={onSubmitChat}>
        <label className="sr-only" htmlFor="chat-message">Ask about this video</label>
        <textarea id="chat-message" rows={3} maxLength={4000} value={chatDraft} disabled={video.ai_status !== "READY" || chatBusy} placeholder="Ask about this video…" onChange={event => onChatDraft(event.target.value)} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); if (chatDraft.trim()) event.currentTarget.form?.requestSubmit(); } }} />
        <div className="chat-form-footer"><span>{chatBusy ? "AI is reviewing…" : `${chatDraft.length}/4,000 · Enter to send · Shift+Enter for a new line`}</span><button type="submit" disabled={video.ai_status !== "READY" || chatBusy || !chatDraft.trim()}>{chatBusy ? "Sending…" : "Send"}</button></div>
        {chatError && <p className="error" role="alert">{chatError}</p>}
      </form>
    </>}
  </aside>;
}
