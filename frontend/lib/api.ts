export type BrandContext = "NONE" | "MRQ";
export type AIStatus = "PROCESSING" | "READY" | "FAILED";
export type Comment = { id: string; video_id: string; timestamp_ms: number; text: string; author: "HUMAN" | "AI"; created_at: string };
export type Message = { id: number; video_id: string; role: "USER" | "ASSISTANT"; text: string; created_at: string };
export type ChatResponse = { user_message: Message; assistant_message: Message; comments: Comment[]; updated_comments: Comment[]; deleted_comment_ids: string[] };
export type Video = { id: string; original_filename: string; mime_type: string; byte_size: number; duration_ms: number; brand_context: BrandContext; ai_status: AIStatus; ai_error: string | null; created_at: string; media_url: string; comments: Comment[]; messages: Message[] };

export class ApiError extends Error {
  constructor(message: string, public readonly code: string | null = null, public readonly retryable: boolean | null = null) {
    super(message);
    this.name = "ApiError";
  }
}

export async function request<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response;
  try { response = await fetch(path, options); }
  catch { throw new Error("Cannot reach the server. Check your connection and try again shortly."); }
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(body?.message ?? `Request failed (${response.status}). Please try again.`, typeof body?.code === "string" ? body.code : null, typeof body?.retryable === "boolean" ? body.retryable : null);
  if (response.status === 204) return undefined as T;
  if (!body) throw new Error("The server returned an unreadable response. Please try again.");
  return body as T;
}

export function formatTime(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}.${String(ms % 1000).padStart(3, "0")}`;
}

export function displayTime(ms: number): string {
  const tenths = Math.floor(ms / 100);
  const seconds = Math.floor(tenths / 10);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}.${tenths % 10}`;
}
