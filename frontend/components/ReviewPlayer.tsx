"use client";

import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import { Comment, displayTime, Video } from "@/lib/api";

export type ReviewPlayerHandle = { getCurrentTimeMs: () => number; seekTo: (ms: number) => void };
type MarkerGroup = { comments: Comment[]; pixel: number };
type Props = { video: Video; selectedCommentId: string | null; onSelectComment: (comment: Comment) => void; onTimeChange: (ms: number) => void; onReadyChange: (ready: boolean) => void; onPlaybackError: () => void };

export const ReviewPlayer = forwardRef<ReviewPlayerHandle, Props>(function ReviewPlayer({ video, selectedCommentId, onSelectComment, onTimeChange, onReadyChange, onPlaybackError }, ref) {
  const media = useRef<HTMLVideoElement>(null);
  const markerRail = useRef<HTMLDivElement>(null);
  const [railWidth, setRailWidth] = useState(0);
  const [currentMs, setCurrentMs] = useState(0);
  const [ready, setReady] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(false);
  const [openGroup, setOpenGroup] = useState<number | null>(null);

  useEffect(() => {
    const rail = markerRail.current;
    if (!rail) return;
    const observer = new ResizeObserver(() => setRailWidth(rail.clientWidth));
    observer.observe(rail);
    setRailWidth(rail.clientWidth);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const updateControls = () => { if (media.current) media.current.controls = document.fullscreenElement === media.current; };
    document.addEventListener("fullscreenchange", updateControls);
    return () => document.removeEventListener("fullscreenchange", updateControls);
  }, []);

  useEffect(() => { setReady(false); setCurrentMs(0); setPlaying(false); setOpenGroup(null); onReadyChange(false); }, [video.id, onReadyChange]);

  function seekTo(ms: number) {
    if (!media.current || !ready) return;
    media.current.pause();
    media.current.currentTime = ms / 1000;
    setCurrentMs(ms);
    onTimeChange(ms);
  }
  useImperativeHandle(ref, () => ({ getCurrentTimeMs: () => Math.round((media.current?.currentTime ?? 0) * 1000), seekTo }));

  const groups = useMemo(() => {
    if (!railWidth || !video.duration_ms) return [];
    const sorted = [...video.comments].sort((a, b) => a.timestamp_ms - b.timestamp_ms);
    const result: MarkerGroup[] = [];
    let lastMarkerPixel = -Infinity;
    for (const comment of sorted) {
      const pixel = comment.timestamp_ms / video.duration_ms * railWidth;
      const last = result[result.length - 1];
      if (last && pixel - lastMarkerPixel < 24) {
        last.comments.push(comment);
        last.pixel = last.comments.reduce((sum, item) => sum + item.timestamp_ms / video.duration_ms * railWidth, 0) / last.comments.length;
      } else result.push({ comments: [comment], pixel });
      lastMarkerPixel = pixel;
    }
    return result;
  }, [video.comments, video.duration_ms, railWidth]);

  function choose(comment: Comment) { setOpenGroup(null); onSelectComment(comment); }
  const progress = video.duration_ms ? Math.min(100, currentMs / video.duration_ms * 100) : 0;
  return <div className="player-shell">
    <div className="video-stage">
      <video key={video.id} ref={media} src={video.media_url} playsInline preload="metadata" onLoadedMetadata={() => { setReady(true); onReadyChange(true); }} onTimeUpdate={event => { const ms = Math.round(event.currentTarget.currentTime * 1000); setCurrentMs(ms); onTimeChange(ms); }} onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onVolumeChange={event => setMuted(event.currentTarget.muted)} onError={() => { setReady(false); onReadyChange(false); onPlaybackError(); }} />
    </div>
    <div className="timeline-area">
      <input className="seek-track" style={{ background: `linear-gradient(to right, #90b7ff ${progress}%, #4a4e59 ${progress}%)` }} aria-label="Review position" type="range" min={0} max={video.duration_ms} step={1} value={currentMs} disabled={!ready} onChange={event => seekTo(Number(event.target.value))} />
      <div ref={markerRail} className="marker-rail" aria-label="Comment positions on the video timeline">
        {groups.map((group, index) => {
          const single = group.comments.length === 1;
          const first = group.comments[0];
          const label = single ? `${first.author === "AI" ? "AI" : "Human"} comment at ${displayTime(first.timestamp_ms)}: ${first.text}` : `${group.comments.length} comments near ${displayTime(first.timestamp_ms)}`;
          const radius = single ? 8 : 12;
          const position = Math.min(Math.max(group.pixel, radius), Math.max(radius, railWidth - radius));
          const edge = position < 140 ? "left-edge" : position > railWidth - 140 ? "right-edge" : "";
          return <div key={`${first.id}-${index}`} className={`marker-position ${edge}`} style={{ left: `${position}px` }}>
            <button type="button" className={`marker ${single ? `marker-${first.author.toLowerCase()}` : "marker-group"} ${single && selectedCommentId === first.id ? "selected" : ""}`} disabled={!ready} aria-label={label} data-preview={label} aria-expanded={single ? undefined : openGroup === index} onClick={() => single ? choose(first) : setOpenGroup(openGroup === index ? null : index)}>{single ? <span className="sr-only">{label}</span> : group.comments.length}</button>
            {!single && openGroup === index && <div className="marker-popover" role="group" aria-label="Comments at this point">{group.comments.map(comment => <button type="button" key={comment.id} onClick={() => choose(comment)}><span>{displayTime(comment.timestamp_ms)} · {comment.author === "AI" ? "AI" : "Human"}</span><small>{comment.text}</small></button>)}</div>}
          </div>;
        })}
      </div>
    </div>
    <div className="player-controls">
      <div className="control-group"><button type="button" disabled={!ready} aria-label={playing ? "Pause" : "Play"} onClick={() => { if (!media.current) return; if (media.current.paused) void media.current.play(); else media.current.pause(); }}>{playing ? "❚❚" : "▶"}</button><button type="button" disabled={!ready} aria-label={muted ? "Unmute" : "Mute"} onClick={() => { if (media.current) media.current.muted = !media.current.muted; }}>{muted ? "Muted" : "Sound"}</button></div>
      <output>{displayTime(currentMs)} / {displayTime(video.duration_ms)}</output>
      <div className="control-group"><button type="button" disabled={!ready} aria-label="Fullscreen video" onClick={() => { if (media.current) void media.current.requestFullscreen(); }}>⛶</button></div>
    </div>
  </div>;
});
