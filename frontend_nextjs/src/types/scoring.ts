/**
 * Type definitions for the AI Pronunciation Scoring API.
 * Endpoint: POST /api/v1/score (multipart/form-data)
 *
 * The API has dual-routing behavior:
 * - Branch A (Read-Aloud): When `target_text` is provided → returns GOP scores
 * - Branch B (Free Decoding): When `target_text` is omitted → returns ASR result
 */

// ─── Branch A: Read-Aloud (Forced Alignment + GOP) ───────────────────────────

export interface WordScore {
  /** The aligned word (uppercase, as decoded by Wav2Vec2) */
  word: string;
  /** Start time of the word in seconds */
  start_time: number;
  /** End time of the word in seconds */
  end_time: number;
  /** Pedagogical pronunciation score for this word (15.0–100.0) */
  score: number;
}

export interface ReadAloudResponse {
  /** Harmonic mean of all word scores, penalizing weak words heavily (15.0–100.0) */
  overall_score: number;
  /** Per-word alignment timestamps and GOP-based pronunciation scores */
  word_scores: WordScore[];
  /** The normalized transcript used for alignment */
  transcript: string;
}

// ─── Branch B: Spontaneous Speech (Free Decoding / ASR) ──────────────────────

export interface FreeDecodingResponse {
  /** The text recognized by the ASR model */
  recognized_text: string;
  /** Estimated fluency score */
  fluency_score: number;
}

// ─── Union Type ──────────────────────────────────────────────────────────────

export type ScoringResponse = ReadAloudResponse | FreeDecodingResponse;

// ─── Type Guards ─────────────────────────────────────────────────────────────

export function isReadAloudResponse(res: ScoringResponse): res is ReadAloudResponse {
  return 'overall_score' in res && 'word_scores' in res;
}

export function isFreeDecodingResponse(res: ScoringResponse): res is FreeDecodingResponse {
  return 'recognized_text' in res && 'fluency_score' in res;
}

// ─── Error Response ──────────────────────────────────────────────────────────

export interface ScoringErrorResponse {
  detail: string;
}
