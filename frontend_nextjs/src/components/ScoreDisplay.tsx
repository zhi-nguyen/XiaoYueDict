'use client';

import React, { useMemo } from 'react';
import type { ScoringResponse } from '@/types/scoring';
import {
  isReadAloudResponse,
  isChineseReadAloudResponse,
  isFreeDecodingResponse,
  isReadAloudAny,
  getScoreLevel,
} from '@/types/scoring';

interface ScoreDisplayProps {
  result: ScoringResponse;
  /** Overall score override (extracted by gateway) */
  overallScore?: number | null;
}

/** Maps score levels to Tailwind-compatible color strings */
const SCORE_COLORS = {
  excellent: { text: 'text-emerald-600', bg: 'bg-emerald-50', border: 'border-emerald-200', ring: '#10B981' },
  good: { text: 'text-blue-600', bg: 'bg-blue-50', border: 'border-blue-200', ring: '#3B82F6' },
  moderate: { text: 'text-amber-600', bg: 'bg-amber-50', border: 'border-amber-200', ring: '#F59E0B' },
  poor: { text: 'text-red-600', bg: 'bg-red-50', border: 'border-red-200', ring: '#EF4444' },
};

/**
 * Premium Score Display — animated circular gauge + word-level breakdown.
 * Supports English (ReadAloud, FreeDecoding) and Chinese (CharacterLevel) responses.
 */
export default function ScoreDisplay({ result, overallScore }: ScoreDisplayProps) {
  // Determine the headline score
  const score = useMemo(() => {
    if (overallScore != null) return overallScore;
    if (isReadAloudAny(result)) return result.overall_score;
    if (isFreeDecodingResponse(result)) return result.fluency_score;
    return 0;
  }, [result, overallScore]);

  const level = getScoreLevel(score);
  const colors = SCORE_COLORS[level];

  // SVG circle parameters
  const radius = 54;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;

  return (
    <div className="animate-slide-up space-y-6">
      {/* ── Score Gauge Card ── */}
      <div className={`rounded-2xl border ${colors.border} ${colors.bg} p-6 shadow-sm`}>
        <div className="flex flex-col sm:flex-row items-center gap-6">
          {/* Circular Gauge */}
          <div className="relative w-[140px] h-[140px] flex-shrink-0">
            <svg className="w-full h-full -rotate-90" viewBox="0 0 120 120">
              {/* Background track */}
              <circle
                cx="60" cy="60" r={radius}
                fill="transparent"
                stroke="currentColor"
                className="text-black/5"
                strokeWidth="8"
              />
              {/* Score arc */}
              <circle
                cx="60" cy="60" r={radius}
                fill="transparent"
                stroke={colors.ring}
                strokeWidth="8"
                strokeLinecap="round"
                strokeDasharray={circumference}
                strokeDashoffset={offset}
                className="animate-progress-stroke"
                style={{
                  '--circumference': circumference,
                  '--target-offset': offset,
                } as React.CSSProperties}
              />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className={`text-4xl font-black ${colors.text} animate-count-appear`}>
                {Math.round(score)}
              </span>
              <span className="text-[10px] font-bold text-secondary uppercase tracking-widest mt-1">
                / 100
              </span>
            </div>
          </div>

          {/* Score Summary */}
          <div className="flex-1 text-center sm:text-left">
            <h3 className={`text-lg font-bold ${colors.text}`}>
              {level === 'excellent' && '🎉 Xuất sắc!'}
              {level === 'good' && '👍 Tốt lắm!'}
              {level === 'moderate' && '💪 Cần cải thiện'}
              {level === 'poor' && '📝 Hãy luyện tập thêm'}
            </h3>

            {isReadAloudAny(result) && (
              <p className="text-secondary text-sm mt-1">
                Đã chấm {result.word_scores.length} từ/ký tự
                {isReadAloudResponse(result) && result.gop_score != null && (
                  <span className="text-xs ml-2 opacity-60">
                    GOP: {result.gop_score} · ML: {result.sentence_score}
                  </span>
                )}
              </p>
            )}

            {isFreeDecodingResponse(result) && (
              <p className="text-secondary text-sm mt-1">
                Điểm lưu loát — Chế độ tự do
              </p>
            )}
          </div>
        </div>
      </div>

      {/* ── Word-Level Breakdown ── */}
      {isReadAloudAny(result) && result.word_scores.length > 0 && (
        <div className="rounded-2xl border border-outline bg-surface p-6 shadow-sm animate-fade-in">
          <h4 className="text-sm font-bold text-primary mb-4 flex items-center gap-2">
            <span className="material-symbols-outlined text-[18px]">analytics</span>
            Chi tiết từng {isChineseReadAloudResponse(result) ? 'ký tự' : 'từ'}
          </h4>

          <div className="flex flex-wrap gap-2">
            {result.word_scores.map((ws, i) => {
              const wLevel = getScoreLevel(ws.score);
              const wColors = SCORE_COLORS[wLevel];

              return (
                <div
                  key={i}
                  className={`group relative inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium border transition-all hover:scale-105 cursor-default ${wColors.bg} ${wColors.border} ${wColors.text}`}
                  style={{ animationDelay: `${i * 50}ms` }}
                >
                  <span className="font-semibold">{ws.word}</span>
                  <span className="opacity-60 text-xs">{Math.round(ws.score)}</span>

                  {/* Pinyin tooltip for Chinese */}
                  {'pinyin' in ws && ws.pinyin && (
                    <span className="absolute -top-8 left-1/2 -translate-x-1/2 px-2 py-1 bg-primary text-white text-[10px] rounded-md opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap pointer-events-none">
                      {ws.pinyin}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* ── Free Decoding Transcript ── */}
      {isFreeDecodingResponse(result) && (
        <div className="rounded-2xl border border-outline bg-surface p-6 shadow-sm animate-fade-in">
          <h4 className="text-sm font-bold text-primary mb-3 flex items-center gap-2">
            <span className="material-symbols-outlined text-[18px]">subtitles</span>
            Văn bản nhận diện
          </h4>
          <p className="text-primary text-lg leading-relaxed font-medium">
            {result.recognized_text}
          </p>
        </div>
      )}

      {/* ── Raw JSON (Collapsible) ── */}
      <details className="group">
        <summary className="cursor-pointer text-xs font-medium text-secondary hover:text-primary transition-colors flex items-center gap-1">
          <span className="material-symbols-outlined text-[14px] group-open:rotate-90 transition-transform">chevron_right</span>
          Xem JSON thô
        </summary>
        <pre className="mt-2 bg-gray-900 text-green-400 text-xs rounded-xl p-4 overflow-x-auto font-mono leading-relaxed max-h-72 overflow-y-auto">
          {JSON.stringify(result, null, 2)}
        </pre>
      </details>
    </div>
  );
}
