'use client';

import { useState, useCallback } from 'react';
import type { ScoringResponse, ScoringErrorResponse } from '@/types/scoring';

/** Base URL for the AI scoring microservice */
const AI_SERVICE_URL = process.env.NEXT_PUBLIC_AI_SERVICE_URL || 'http://localhost:8000';

interface UsePronunciationScorerReturn {
  /** Triggers the scoring request */
  scoreAudio: (audioBlob: Blob, targetText?: string) => Promise<ScoringResponse | null>;
  /** The latest successful response from the API */
  result: ScoringResponse | null;
  /** Whether a request is currently in-flight */
  isLoading: boolean;
  /** Error message from the last failed request, or null */
  error: string | null;
  /** Resets the hook state to its initial values */
  reset: () => void;
}

/**
 * Custom hook to interact with the AI Pronunciation Scoring API.
 *
 * Usage:
 * ```tsx
 * const { scoreAudio, result, isLoading, error } = usePronunciationScorer();
 * await scoreAudio(myWavBlob, "Hello world");
 * ```
 *
 * CRITICAL: This hook does NOT manually set the Content-Type header.
 * The browser must auto-set it with the correct multipart boundary.
 */
export function usePronunciationScorer(): UsePronunciationScorerReturn {
  const [result, setResult] = useState<ScoringResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reset = useCallback(() => {
    setResult(null);
    setIsLoading(false);
    setError(null);
  }, []);

  const scoreAudio = useCallback(async (
    audioBlob: Blob,
    targetText?: string
  ): Promise<ScoringResponse | null> => {
    setIsLoading(true);
    setError(null);
    setResult(null);

    try {
      // ── Build multipart form ──────────────────────────────────────────
      const formData = new FormData();
      formData.append('audio_file', audioBlob, 'recording.wav');

      // Conditionally append target_text for Read-Aloud (Branch A) routing
      if (targetText && targetText.trim() !== '') {
        formData.append('target_text', targetText.trim());
      }

      // ── Send request ──────────────────────────────────────────────────
      // Do NOT set Content-Type manually — the browser auto-generates
      // the correct `multipart/form-data; boundary=----...` header.
      const response = await fetch(`${AI_SERVICE_URL}/api/v1/score`, {
        method: 'POST',
        body: formData,
      });

      // ── Handle HTTP errors ────────────────────────────────────────────
      if (!response.ok) {
        let errorMessage = `Server error (${response.status})`;
        try {
          const errorData: ScoringErrorResponse = await response.json();
          errorMessage = errorData.detail || errorMessage;
        } catch {
          // Response body wasn't JSON, use the generic error
        }
        throw new Error(errorMessage);
      }

      // ── Parse successful response ─────────────────────────────────────
      const data: ScoringResponse = await response.json();
      setResult(data);
      return data;

    } catch (err) {
      const message = err instanceof Error
        ? err.message
        : 'An unexpected error occurred while scoring.';
      setError(message);
      console.error('[usePronunciationScorer] Scoring failed:', err);
      return null;

    } finally {
      setIsLoading(false);
    }
  }, []);

  return { scoreAudio, result, isLoading, error, reset };
}
