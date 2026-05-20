'use client';

import React, { useState, useRef } from 'react';
import { usePronunciationScorer } from '@/hooks/usePronunciationScorer';
import { isReadAloudResponse } from '@/types/scoring';

/**
 * Helper: Convert an AudioBuffer to a 16-bit PCM WAV Blob.
 * Re-used from AudioRecorder — extracted here for self-containment.
 */
function audioBufferToWav(buffer: AudioBuffer): Blob {
  const numChannels = 1;
  const sampleRate = buffer.sampleRate;
  const samples = buffer.getChannelData(0);
  const bitDepth = 16;
  const dataLength = samples.length * (bitDepth / 8);
  const bufferLength = 44 + dataLength;
  const arrayBuffer = new ArrayBuffer(bufferLength);
  const view = new DataView(arrayBuffer);

  const writeStr = (offset: number, str: string) => {
    for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i));
  };

  writeStr(0, 'RIFF');
  view.setUint32(4, 36 + dataLength, true);
  writeStr(8, 'WAVE');
  writeStr(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, numChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * numChannels * (bitDepth / 8), true);
  view.setUint16(32, numChannels * (bitDepth / 8), true);
  view.setUint16(34, bitDepth, true);
  writeStr(36, 'data');
  view.setUint32(40, dataLength, true);

  let offset = 44;
  for (let i = 0; i < samples.length; i++, offset += 2) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }

  return new Blob([view], { type: 'audio/wav' });
}

export default function ScoringTest() {
  const { scoreAudio, result, isLoading, error, reset } = usePronunciationScorer();

  const [targetText, setTargetText] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // ── Microphone Recording ──────────────────────────────────────────────────

  const startRecording = async () => {
    try {
      reset();
      setAudioBlob(null);
      chunksRef.current = [];

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const webmBlob = new Blob(chunksRef.current, { type: 'audio/webm' });

        try {
          const arrayBuffer = await webmBlob.arrayBuffer();
          const ctx = new (window.AudioContext || (window as any).webkitAudioContext)();
          const decoded = await ctx.decodeAudioData(arrayBuffer);
          const wavBlob = audioBufferToWav(decoded);
          setAudioBlob(wavBlob);
        } catch {
          setAudioBlob(webmBlob); // fallback — let the server handle it
        }
      };

      recorder.start();
      setIsRecording(true);
    } catch {
      alert('Microphone access denied or unavailable.');
    }
  };

  const stopRecording = () => {
    mediaRecorderRef.current?.stop();
    setIsRecording(false);
  };

  // ── File Upload ───────────────────────────────────────────────────────────

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      reset();
      setAudioBlob(file);
    }
  };

  // ── Submit ────────────────────────────────────────────────────────────────

  const handleSubmit = async () => {
    if (!audioBlob) return;
    await scoreAudio(audioBlob, targetText || undefined);
  };

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="w-full max-w-2xl mx-auto mt-8 space-y-6">
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <div className="text-center">
        <h2 className="text-2xl font-bold text-gray-800">
          Scoring API Test
        </h2>
        <p className="mt-1 text-sm text-gray-500">
          Direct test against <code className="text-xs bg-gray-100 px-1.5 py-0.5 rounded font-mono">POST /api/v1/score</code>
        </p>
      </div>

      <div className="bg-white rounded-2xl shadow-lg border border-gray-100 p-6 space-y-5">
        {/* ── Target Text (Optional) ─────────────────────────────────── */}
        <div>
          <label htmlFor="scoring-target-text" className="block text-sm font-semibold text-gray-700 mb-1.5">
            Target Text <span className="font-normal text-gray-400">(optional — leave empty for Free Decoding)</span>
          </label>
          <textarea
            id="scoring-target-text"
            rows={3}
            value={targetText}
            onChange={(e) => setTargetText(e.target.value)}
            placeholder="e.g. The quick brown fox jumps over the lazy dog"
            className="w-full rounded-xl border border-gray-200 bg-gray-50 px-4 py-3 text-sm text-gray-800
                       placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-400
                       focus:border-transparent resize-none transition-shadow"
          />
          <p className="mt-1 text-xs text-gray-400">
            {targetText.trim()
              ? ' Read-Aloud mode — strict GOP scoring per word'
              : ' Free Decoding mode — ASR transcription + fluency'}
          </p>
        </div>

        {/* ── Audio Input ────────────────────────────────────────────── */}
        <div className="flex flex-col sm:flex-row gap-3">
          {/* Record button */}
          <button
            id="scoring-record-btn"
            type="button"
            onClick={isRecording ? stopRecording : startRecording}
            disabled={isLoading}
            className={`flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl font-medium text-sm
                        transition-all focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:opacity-50
                        ${isRecording
                ? 'bg-red-500 hover:bg-red-600 text-white focus:ring-red-400 animate-pulse'
                : 'bg-gray-100 hover:bg-gray-200 text-gray-700 focus:ring-gray-400'}`}
          >
            {isRecording ? (
              <>
                <span className="w-3 h-3 bg-white rounded-sm" />
                Stop Recording
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M7 4a3 3 0 016 0v4a3 3 0 11-6 0V4zm4 10.93A7.001 7.001 0 0017 8h-2a5 5 0 01-10 0H3a7.001 7.001 0 006 6.93V17H6v2h8v-2h-3v-2z" clipRule="evenodd" />
                </svg>
                Record
              </>
            )}
          </button>

          {/* Upload button */}
          <input
            type="file"
            accept="audio/*"
            ref={fileInputRef}
            onChange={handleFileUpload}
            className="hidden"
          />
          <button
            id="scoring-upload-btn"
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={isLoading || isRecording}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl font-medium text-sm
                       bg-gray-100 hover:bg-gray-200 text-gray-700 transition-all focus:outline-none
                       focus:ring-2 focus:ring-offset-2 focus:ring-gray-400 disabled:opacity-50"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
            Upload File
          </button>
        </div>

        {/* Audio ready indicator */}
        {audioBlob && (
          <p className="text-xs text-green-600 font-medium flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-green-500 inline-block" />
            Audio ready — {(audioBlob.size / 1024).toFixed(1)} KB
          </p>
        )}

        {/* ── Submit Button ──────────────────────────────────────────── */}
        <button
          id="scoring-submit-btn"
          type="button"
          onClick={handleSubmit}
          disabled={!audioBlob || isLoading}
          className="w-full py-3 rounded-xl font-semibold text-sm transition-all focus:outline-none
                     focus:ring-2 focus:ring-offset-2 focus:ring-blue-400 disabled:opacity-40
                     disabled:cursor-not-allowed bg-blue-600 hover:bg-blue-700 text-white shadow-md
                     hover:shadow-lg active:scale-[0.98]"
        >
          {isLoading ? (
            <span className="flex items-center justify-center gap-2">
              <svg className="animate-spin w-4 h-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              Scoring…
            </span>
          ) : (
            `Submit for ${targetText.trim() ? 'Read-Aloud Scoring' : 'Free Decoding'}`
          )}
        </button>
      </div>

      {/* ── Error Display ──────────────────────────────────────────────── */}
      {error && (
        <div id="scoring-error" className="bg-red-50 border border-red-200 rounded-xl px-5 py-4">
          <p className="text-sm font-semibold text-red-700">❌ Error</p>
          <p className="text-sm text-red-600 mt-1">{error}</p>
        </div>
      )}

      {/* ── Result Display ─────────────────────────────────────────────── */}
      {result && (
        <div id="scoring-result" className="space-y-4">
          {/* Quick summary card */}
          {isReadAloudResponse(result) && (
            <div className="bg-gradient-to-br from-blue-50 to-indigo-50 border border-blue-200 rounded-xl px-5 py-4">
              <p className="text-xs font-semibold text-blue-500 uppercase tracking-wider mb-1">
                Read-Aloud Score
              </p>
              <p className="text-4xl font-black text-blue-700">
                {result.overall_score}
                <span className="text-lg font-medium text-blue-400 ml-1">/ 100</span>
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                {result.word_scores.map((ws, i) => (
                  <span
                    key={i}
                    className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold
                      ${ws.score >= 80
                        ? 'bg-green-100 text-green-700'
                        : ws.score >= 50
                          ? 'bg-yellow-100 text-yellow-700'
                          : 'bg-red-100 text-red-700'}`}
                  >
                    {ws.word}
                    <span className="opacity-70">{ws.score}</span>
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Raw JSON */}
          <details className="group">
            <summary className="cursor-pointer text-xs font-medium text-gray-500 hover:text-gray-700 transition-colors">
              📋 View raw JSON response
            </summary>
            <pre
              id="scoring-raw-json"
              className="mt-2 bg-gray-900 text-green-400 text-xs rounded-xl p-4 overflow-x-auto
                         font-mono leading-relaxed max-h-96 overflow-y-auto"
            >
              {JSON.stringify(result, null, 2)}
            </pre>
          </details>
        </div>
      )}
    </div>
  );
}
