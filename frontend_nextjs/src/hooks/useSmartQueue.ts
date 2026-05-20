'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import type {
  TaskSubmitResponse,
  TaskStatusResponse,
  ScoringResponse,
} from '@/types/scoring';

/** Base URL for the Django Gateway API */
const GATEWAY_URL = process.env.NEXT_PUBLIC_GATEWAY_URL || 'http://localhost';

export type QueuePhase =
  | 'idle'
  | 'uploading'
  | 'queued'
  | 'processing'
  | 'completed'
  | 'error';

export interface UseSmartQueueReturn {
  /** Submit audio for scoring through the Django gateway */
  submit: (audioBlob: Blob, language: 'en' | 'zh', targetText?: string) => Promise<void>;
  /** Current phase of the queue lifecycle */
  phase: QueuePhase;
  /** Queue position (0 = not in queue or being processed) */
  queuePosition: number;
  /** Estimated wait in seconds */
  estimatedWait: number;
  /** The full scoring result when completed */
  resultData: ScoringResponse | null;
  /** Overall score extracted for quick display */
  score: number | null;
  /** Error message if phase is 'error' */
  errorMessage: string | null;
  /** Task ID for reference */
  taskId: string | null;
  /** Reset everything back to idle */
  reset: () => void;
}

const POLL_INTERVAL_MS = 2000;

/**
 * Smart Queue hook — handles the full async scoring lifecycle:
 * 1. Upload audio to Django gateway
 * 2. Receive task_id + initial queue position
 * 3. Poll for status updates
 * 4. Transition through phases: idle → uploading → queued → processing → completed/error
 */
export function useSmartQueue(): UseSmartQueueReturn {
  const [phase, setPhase] = useState<QueuePhase>('idle');
  const [queuePosition, setQueuePosition] = useState(0);
  const [estimatedWait, setEstimatedWait] = useState(0);
  const [resultData, setResultData] = useState<ScoringResponse | null>(null);
  const [score, setScore] = useState<number | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);

  const pollingRef = useRef<NodeJS.Timeout | null>(null);
  const isMountedRef = useRef(true);

  // Cleanup on unmount
  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, []);

  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  const reset = useCallback(() => {
    stopPolling();
    setPhase('idle');
    setQueuePosition(0);
    setEstimatedWait(0);
    setResultData(null);
    setScore(null);
    setErrorMessage(null);
    setTaskId(null);
  }, [stopPolling]);

  const startPolling = useCallback((id: string) => {
    stopPolling();

    const poll = async () => {
      if (!isMountedRef.current) return;

      try {
        const res = await fetch(`${GATEWAY_URL}/api/core/assessments/status/${id}/`);

        if (!res.ok) {
          throw new Error(`Status check failed (${res.status})`);
        }

        const data: TaskStatusResponse = await res.json();

        if (!isMountedRef.current) return;

        // Update queue position
        setQueuePosition(data.queue_position);
        setEstimatedWait(data.estimated_wait_seconds);

        switch (data.status) {
          case 'PENDING':
            setPhase(data.queue_position <= 4 ? 'processing' : 'queued');
            break;

          case 'PROCESSING':
            setPhase('processing');
            setQueuePosition(Math.min(data.queue_position, 1));
            break;

          case 'COMPLETED':
            setPhase('completed');
            setResultData(data.result_data);
            setScore(data.score);
            stopPolling();
            break;

          case 'FAILED':
            setPhase('error');
            setErrorMessage(data.error_message || 'Processing failed on the server.');
            stopPolling();
            break;
        }
      } catch (err) {
        console.error('[useSmartQueue] Polling error:', err);
        // Don't stop polling on transient network errors — retry next cycle
      }
    };

    // Initial poll immediately
    poll();

    // Then poll on interval
    pollingRef.current = setInterval(poll, POLL_INTERVAL_MS);
  }, [stopPolling]);

  const submit = useCallback(async (
    audioBlob: Blob,
    language: 'en' | 'zh',
    targetText?: string,
  ) => {
    // Reset state for new submission
    reset();
    setPhase('uploading');

    try {
      const formData = new FormData();
      formData.append('audio', audioBlob, 'recording.wav');
      formData.append('language', language);

      if (targetText && targetText.trim()) {
        formData.append('target_text', targetText.trim());
      }

      const res = await fetch(`${GATEWAY_URL}/api/core/assessments/submit/`, {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        const errBody = await res.json().catch(() => ({ error: 'Upload failed' }));
        throw new Error(errBody.error || `Server error (${res.status})`);
      }

      const data: TaskSubmitResponse = await res.json();

      if (!isMountedRef.current) return;

      setTaskId(data.task_id);
      setQueuePosition(data.queue_position);
      setEstimatedWait(data.estimated_wait_seconds);

      // Determine initial phase based on queue position
      if (data.queue_position <= 4) {
        setPhase('processing');
      } else {
        setPhase('queued');
      }

      // Start polling for results
      startPolling(data.task_id);

    } catch (err) {
      if (!isMountedRef.current) return;
      const message = err instanceof Error ? err.message : 'Failed to submit audio.';
      setPhase('error');
      setErrorMessage(message);
      console.error('[useSmartQueue] Submit failed:', err);
    }
  }, [reset, startPolling]);

  return {
    submit,
    phase,
    queuePosition,
    estimatedWait,
    resultData,
    score,
    errorMessage,
    taskId,
    reset,
  };
}
