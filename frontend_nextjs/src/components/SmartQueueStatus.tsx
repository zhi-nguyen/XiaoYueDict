'use client';

import React from 'react';
import type { QueuePhase } from '@/hooks/useSmartQueue';

interface SmartQueueStatusProps {
  phase: QueuePhase;
  queuePosition: number;
  estimatedWait: number;
}

/**
 * Smart Queue Status Display.
 * Position 1-4:  "Analyzing pronunciation..." with animated pulse
 * Position 5-15: Queue position + estimated time
 * Position 15+:  "High demand" message
 */
export default function SmartQueueStatus({
  phase,
  queuePosition,
  estimatedWait,
}: SmartQueueStatusProps) {
  if (phase === 'idle' || phase === 'completed' || phase === 'error') {
    return null;
  }

  return (
    <div className="animate-slide-up">
      <div className="relative overflow-hidden rounded-2xl border border-outline bg-surface p-6 shadow-sm">
        {/* Shimmer overlay */}
        <div className="absolute inset-0 animate-shimmer opacity-30 pointer-events-none" />

        <div className="relative z-10">
          {/* Uploading */}
          {phase === 'uploading' && (
            <div className="flex items-center gap-4">
              <div className="w-10 h-10 rounded-full bg-hover-bg flex items-center justify-center">
                <svg className="animate-spin w-5 h-5 text-primary" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
              </div>
              <div>
                <p className="font-semibold text-primary text-sm">Đang tải lên...</p>
                <p className="text-secondary text-xs mt-0.5">Đang gửi file âm thanh đến máy chủ</p>
              </div>
            </div>
          )}

          {/* Processing (position 1-4) */}
          {phase === 'processing' && (
            <div className="flex items-center gap-4">
              <div className="relative w-10 h-10 flex items-center justify-center">
                {/* Animated waveform bars */}
                <div className="flex items-center gap-[3px] h-6">
                  {[0, 1, 2, 3, 4].map((i) => (
                    <div
                      key={i}
                      className="w-[3px] bg-gradient-to-t from-[var(--accent-gradient-start)] to-[var(--accent-gradient-end)] rounded-full animate-wave-bar"
                      style={{
                        height: '100%',
                        animationDelay: `${i * 0.15}s`,
                        animationDuration: `${0.8 + i * 0.1}s`,
                      }}
                    />
                  ))}
                </div>
              </div>
              <div>
                <p className="font-semibold text-primary text-sm">
                  Đang phân tích phát âm...
                </p>
                <p className="text-secondary text-xs mt-0.5">
                  AI đang chấm điểm từng từ trong câu của bạn
                </p>
              </div>
            </div>
          )}

          {/* Queued (position 5-15) */}
          {phase === 'queued' && queuePosition <= 15 && (
            <div className="flex items-center gap-4">
              <div className="relative w-12 h-12 rounded-full bg-gradient-to-br from-[var(--accent-gradient-start)] to-[var(--accent-gradient-end)] flex items-center justify-center shadow-md">
                <span className="text-white font-bold text-lg">{queuePosition}</span>
              </div>
              <div className="flex-1">
                <p className="font-semibold text-primary text-sm">
                  Vị trí hàng đợi: #{queuePosition}
                </p>
                <p className="text-secondary text-xs mt-0.5">
                  Thời gian chờ ước tính: ~{estimatedWait}s
                </p>
                {/* Progress bar */}
                <div className="mt-3 h-1.5 bg-hover-bg rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-[var(--accent-gradient-start)] to-[var(--accent-gradient-end)] rounded-full transition-all duration-1000"
                    style={{ width: `${Math.max(5, 100 - (queuePosition / 15) * 100)}%` }}
                  />
                </div>
              </div>
            </div>
          )}

          {/* Queued (position > 15) */}
          {phase === 'queued' && queuePosition > 15 && (
            <div className="flex items-center gap-4">
              <div className="w-10 h-10 rounded-full bg-orange/10 flex items-center justify-center">
                <span className="material-symbols-outlined text-orange text-xl">hourglass_top</span>
              </div>
              <div>
                <p className="font-semibold text-primary text-sm">
                  Hệ thống đang bận — Vị trí #{queuePosition}
                </p>
                <p className="text-secondary text-xs mt-0.5">
                  Thời gian chờ ước tính: ~{Math.round(estimatedWait / 60)} phút.
                  Cảm ơn bạn đã kiên nhẫn!
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
