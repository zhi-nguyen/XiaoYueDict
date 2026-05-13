/**
 * Type definitions for the XiaoYueDict Pronunciation Scoring System.
 *
 * Covers both English (Wav2Vec2 GOP) and Chinese (Sherpa-ONNX) scoring,
 * as well as the Django gateway task management types.
 */

// ─── Task Management (Django Gateway) ─────────────────────────────────────────

/** Response from POST /api/v1/assessments/submit/ */
export interface TaskSubmitResponse {
  task_id: string;
  queue_position: number;
  estimated_wait_seconds: number;
}

/** Response from GET /api/v1/assessments/status/<task_id>/ */
export interface TaskStatusResponse {
  id: string;
  status: 'PENDING' | 'PROCESSING' | 'COMPLETED' | 'FAILED';
  language: 'en' | 'zh';
  score: number | null;
  result_data: ScoringResponse | null;
  error_message: string;
  queue_position: number;
  estimated_wait_seconds: number;
  created_at: string;
}

// ─── Branch A: Read-Aloud (English — Forced Alignment + GOP) ─────────────────

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
  /** Harmonic mean of all word scores (15.0–100.0) */
  overall_score: number;
  /** Per-word alignment timestamps and GOP-based pronunciation scores */
  word_scores: WordScore[];
  /** The normalized transcript used for alignment */
  transcript: string;
  /** GOP sub-score (if ONNX blending active) */
  gop_score?: number;
  /** ONNX sentence sub-score (if available) */
  sentence_score?: number;
}

// ─── Branch A: Read-Aloud (Chinese — Character-Level Scoring) ────────────────

export interface ChineseWordScore {
  /** The Chinese character */
  word: string;
  start_time: number;
  end_time: number;
  /** Character pronunciation score (15.0–100.0) */
  score: number;
  /** Pinyin with tone number (e.g., "xue2") */
  pinyin: string;
  /** Tone number (1-4, 0 = unknown) */
  tone: number;
  /** Whether the character was correctly recognized */
  matched: boolean;
}

export interface ChineseReadAloudResponse {
  overall_score: number;
  word_scores: ChineseWordScore[];
  transcript: string;
  target_text: string;
  language: 'zh';
}

// ─── Branch B: Free Decoding (ASR) ───────────────────────────────────────────

export interface FreeDecodingResponse {
  /** The text recognized by the ASR model */
  recognized_text: string;
  /** Estimated fluency score */
  fluency_score: number;
  /** Language identifier */
  language?: 'en' | 'zh';
}

// ─── Union Types ─────────────────────────────────────────────────────────────

export type ScoringResponse =
  | ReadAloudResponse
  | ChineseReadAloudResponse
  | FreeDecodingResponse;

// ─── Type Guards ─────────────────────────────────────────────────────────────

export function isReadAloudResponse(res: ScoringResponse): res is ReadAloudResponse {
  return 'overall_score' in res && 'word_scores' in res && !('language' in res && (res as any).language === 'zh');
}

export function isChineseReadAloudResponse(res: ScoringResponse): res is ChineseReadAloudResponse {
  return 'overall_score' in res && 'word_scores' in res && 'language' in res && (res as any).language === 'zh';
}

export function isFreeDecodingResponse(res: ScoringResponse): res is FreeDecodingResponse {
  return 'recognized_text' in res && 'fluency_score' in res;
}

export function isReadAloudAny(res: ScoringResponse): res is ReadAloudResponse | ChineseReadAloudResponse {
  return 'overall_score' in res && 'word_scores' in res;
}

// ─── Error Response ──────────────────────────────────────────────────────────

export interface ScoringErrorResponse {
  detail: string;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** Returns a CSS-friendly color class name based on score range */
export function getScoreLevel(score: number): 'excellent' | 'good' | 'moderate' | 'poor' {
  if (score >= 85) return 'excellent';
  if (score >= 70) return 'good';
  if (score >= 50) return 'moderate';
  return 'poor';
}
