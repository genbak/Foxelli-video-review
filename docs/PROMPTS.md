# Prompt design

[backend/app/prompts.py](../backend/app/prompts.py) contains the active instructions. The exact request sent by **Review full video** selects the first-pass prompt. Other requests use the chat prompt through the same API path.

## First review

The prompt asks Gemini to inspect the whole video and audio, prioritizing:

- credibility of people, expressions, environments and product imagery;
- believable objects and readable text;
- focus, sharpness and color;
- natural voice/audio delivery;
- whether the visuals demonstrate the narration;
- useful variety.

These priorities guide judgment rather than require a comment in every category. Important hook, staging, pacing, cut or CTA findings are still allowed.

Five short comments from supplied reviews demonstrate the editor's tone. They have no timestamps or filenames, and the instructions distinguish them from findings about the current video. Their presence means the supplied videos are development examples, not an independent accuracy benchmark.

A comment should identify one worthwhile issue at a moment where it can be inspected. A suggested fix is optional. The response includes a neutral one-sentence summary and short timeline notes, without a requested comment count.

Subjective impressions such as unnatural, robotic, pale or AI-looking are allowed. The prompt separates those judgments from factual claims about production methods, exact timing or unreadable details.

## Follow-up chat

The chat prompt focuses on the user's question and existing feedback. Saved comments and earlier answers are opinions to reconsider against the video.

Discussion produces no comment actions. Explicit requests can add feedback or revise, move or remove an existing AI comment by its ID. The AI cannot change Human comments. Chat cannot see the player's current position.

## Input

`backend/app/chat_service.py` builds each request from:

1. The prepared original video at 5 FPS/high media resolution.
2. The full visual MRQ PDF, only for MRQ.
3. The applicable General/MRQ instruction.
4. Verified duration, selected context and all current Human/AI comments with IDs.
5. Up to 20 recent conversation messages.
6. The latest user request.

The MRQ instruction distinguishes applicable brand guidance from historical offers, email-only rules and example layouts. General requests supply no authoritative brand guide.

Video, PDF and saved text are treated as evidence, not instructions.

## Generation and validation

Default model: `gemini-3.8-flash`, using `google-genai==2.25.0`. The request leaves temperature, top-p and top-k at provider defaults, with an 8,192-token output ceiling and a 120-second timeout.

The structured response contains:

- `message`: a review summary or direct chat answer;
- `actions`: zero to ten `add_comment`, `edit_comment` or `delete_comment` actions;
- `timestamp_seconds`: a finite time within the video for a new or moved comment;
- `comment_id`: the ID of an existing AI comment to edit or remove;
- `text`: one short observation with an optional suggestion when adding or revising a comment.

Ten is a safety ceiling, not a target. The backend requires a complete response and validates every action before saving messages and comments together. These checks cannot establish that a finding is factually correct.

Reference documentation: [video understanding](https://ai.google.dev/gemini-api/docs/video-understanding), [media resolution](https://ai.google.dev/gemini-api/docs/media-resolution), [model guidance](https://ai.google.dev/gemini-api/docs/latest-model).
