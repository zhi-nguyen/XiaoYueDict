"use client";

import React, { useState, useRef, useCallback } from 'react';
import { useSmartQueue } from '@/hooks/useSmartQueue';
import SmartQueueStatus from '@/components/SmartQueueStatus';
import ScoreDisplay from '@/components/ScoreDisplay';
import AudioWaveform from '@/components/AudioWaveform';

/** Convert AudioBuffer to 16-bit PCM WAV Blob */
function audioBufferToWav(buffer: AudioBuffer): Blob {
  const sampleRate = buffer.sampleRate;
  const samples = buffer.getChannelData(0);
  const bitDepth = 16;
  const dataLength = samples.length * (bitDepth / 8);
  const bufferLength = 44 + dataLength;
  const ab = new ArrayBuffer(bufferLength);
  const view = new DataView(ab);
  const w = (o: number, s: string) => { for (let i = 0; i < s.length; i++) view.setUint8(o + i, s.charCodeAt(i)); };
  w(0, 'RIFF'); view.setUint32(4, 36 + dataLength, true); w(8, 'WAVE'); w(12, 'fmt ');
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true); view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true); view.setUint16(34, 16, true); w(36, 'data');
  view.setUint32(40, dataLength, true);
  let off = 44;
  for (let i = 0; i < samples.length; i++, off += 2) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(off, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([view], { type: 'audio/wav' });
}

export default function PracticeHub() {
  const queue = useSmartQueue();
  const [isRecording, setIsRecording] = useState(false);
  const [activeStream, setActiveStream] = useState<MediaStream | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);

  const startRecording = useCallback(async () => {
    try {
      queue.reset();
      chunksRef.current = [];
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      setActiveStream(stream);
      const recorder = new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.onstop = async () => {
        stream.getTracks().forEach(t => t.stop());
        setActiveStream(null);
        const webmBlob = new Blob(chunksRef.current, { type: 'audio/webm' });
        try {
          const ab = await webmBlob.arrayBuffer();
          const ctx = new (window.AudioContext || (window as any).webkitAudioContext)();
          const decoded = await ctx.decodeAudioData(ab);
          const wavBlob = audioBufferToWav(decoded);
          // Auto-submit after recording
          await queue.submit(wavBlob, 'en');
        } catch {
          await queue.submit(webmBlob, 'en');
        }
      };

      recorder.start();
      setIsRecording(true);
    } catch {
      alert('Không thể truy cập microphone.');
    }
  }, [queue]);

  const stopRecording = useCallback(() => {
    mediaRecorderRef.current?.stop();
    setIsRecording(false);
  }, []);

  const isBusy = queue.phase !== 'idle' && queue.phase !== 'completed' && queue.phase !== 'error';
  const showResult = queue.phase === 'completed' && queue.resultData;

  // Get display score
  const displayScore = queue.score != null ? Math.round(queue.score) : '--';
  const circumference = 2 * Math.PI * 54;
  const scoreNum = typeof displayScore === 'number' ? displayScore : 0;
  const dashOffset = circumference - (scoreNum / 100) * circumference;

  return (
    <div className="space-y-6">
      {/* Pronunciation Practice Card */}
      <div className="bg-surface border border-outline rounded-[1.5rem] p-8 shadow-sm">
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-hover-bg flex items-center justify-center text-primary">
              <span className="material-symbols-outlined text-[20px]">graphic_eq</span>
            </div>
            <h2 className="text-xl font-bold text-primary">Chấm điểm phát âm AI</h2>
          </div>
          <span className="px-3 py-1 bg-green-100 text-green-700 text-[10px] font-bold rounded-full uppercase tracking-wider">
            Đang hoạt động
          </span>
        </div>

        <div className="flex flex-col md:flex-row items-center gap-8 mb-8">
          {/* Score Circle */}
          <div className="relative w-[120px] h-[120px] flex items-center justify-center shrink-0">
            <svg className="w-full h-full -rotate-90">
              <circle cx="60" cy="60" r="54" fill="transparent" stroke="var(--color-outline)" strokeWidth="6" />
              <circle
                cx="60" cy="60" r="54" fill="transparent"
                stroke={scoreNum >= 85 ? 'var(--score-excellent)' : scoreNum >= 70 ? 'var(--score-good)' : scoreNum >= 50 ? 'var(--score-moderate)' : scoreNum > 0 ? 'var(--score-poor)' : 'var(--color-outline)'}
                strokeWidth="6"
                strokeDasharray={circumference}
                strokeDashoffset={scoreNum > 0 ? dashOffset : circumference}
                strokeLinecap="round"
                className="transition-all duration-1000"
              />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-[28px] font-bold text-primary leading-none mb-1">
                {displayScore}<span className="text-base text-secondary">/100</span>
              </span>
              <span className="text-[10px] font-bold text-secondary uppercase tracking-widest">
                Điểm số
              </span>
            </div>
          </div>

          {/* Waveform & Mic Button */}
          <div className="flex-1 w-full flex flex-col items-center gap-6">
            <AudioWaveform
              isRecording={isRecording}
              stream={activeStream}
              height={64}
            />

            <button
              onClick={isRecording ? stopRecording : startRecording}
              disabled={isBusy}
              className={`relative w-14 h-14 rounded-full flex items-center justify-center shadow-md transition-all disabled:opacity-40 ${
                isRecording
                  ? 'bg-red-500 hover:bg-red-600 text-white'
                  : 'bg-primary text-white hover:bg-primary/90'
              }`}
            >
              {isRecording && <span className="absolute inset-0 rounded-full animate-pulse-ring text-red-300" />}
              <span className="material-symbols-outlined text-[28px]">
                {isRecording ? 'stop' : 'mic'}
              </span>
            </button>
          </div>
        </div>

        {/* Smart Queue Status */}
        {isBusy && (
          <div className="mb-6">
            <SmartQueueStatus
              phase={queue.phase}
              queuePosition={queue.queuePosition}
              estimatedWait={queue.estimatedWait}
            />
          </div>
        )}

        {/* Score Result */}
        {showResult && queue.resultData && (
          <div className="mb-6">
            <ScoreDisplay result={queue.resultData} overallScore={queue.score} />
          </div>
        )}

        {/* Error */}
        {queue.phase === 'error' && (
          <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-xl">
            <p className="text-sm text-red-700">{queue.errorMessage}</p>
            <button onClick={queue.reset} className="mt-2 text-xs font-semibold text-red-700 underline">
              Thử lại
            </button>
          </div>
        )}

        {/* Feedback Chips — show when we have a result */}
        {showResult && (
          <div className="grid grid-cols-2 gap-4">
            <div className="p-4 bg-green-50/50 border border-green-100 rounded-xl flex items-center gap-3">
              <span className="material-symbols-outlined text-green-600 text-[20px]">check_circle</span>
              <span className="font-semibold text-sm text-green-800">
                {scoreNum >= 70 ? 'Phát âm tốt' : 'Cần luyện tập thêm'}
              </span>
            </div>
            <div className="p-4 bg-orange-50/50 border border-orange-100 rounded-xl flex items-center gap-3">
              <span className="material-symbols-outlined text-orange text-[20px]">info</span>
              <span className="font-semibold text-sm text-orange-800">
                {scoreNum >= 85 ? 'Tiếp tục phát huy!' : 'Chú ý phát âm rõ hơn'}
              </span>
            </div>
          </div>
        )}

        {/* Static feedback when no result */}
        {!showResult && queue.phase === 'idle' && (
          <div className="grid grid-cols-2 gap-4">
            <div className="p-4 bg-hover-bg border border-outline/50 rounded-xl flex items-center gap-3">
              <span className="material-symbols-outlined text-secondary text-[20px]">mic</span>
              <span className="font-semibold text-sm text-secondary">Nhấn mic để bắt đầu</span>
            </div>
            <div className="p-4 bg-hover-bg border border-outline/50 rounded-xl flex items-center gap-3">
              <span className="material-symbols-outlined text-secondary text-[20px]">info</span>
              <span className="font-semibold text-sm text-secondary">AI chấm điểm tự động</span>
            </div>
          </div>
        )}
      </div>

      {/* Handwriting Practice Card — kept from original */}
      <div className="bg-surface border border-outline rounded-[1.5rem] p-8 shadow-sm">
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-hover-bg flex items-center justify-center text-primary">
              <span className="material-symbols-outlined text-[20px]">draw</span>
            </div>
            <h2 className="text-xl font-bold text-primary">Chấm điểm nét chữ AI</h2>
          </div>
          <div className="px-3 py-1 bg-hover-bg text-primary text-[10px] font-bold rounded-full uppercase tracking-wider">
            85% Chính xác
          </div>
        </div>

        <div className="mb-6 relative w-full aspect-[2/1] rounded-2xl overflow-hidden border border-outline bg-hover-bg grid-canvas flex items-center justify-center">
          <svg className="absolute inset-0 w-full h-full opacity-40" viewBox="0 0 400 200">
            <path d="M 120 50 C 180 40, 240 45, 280 55 M 200 40 L 200 160 M 150 160 C 180 155, 220 165, 250 155" fill="none" stroke="var(--color-primary)" strokeWidth="6" strokeLinecap="round" strokeLinejoin="round"></path>
          </svg>
          <span className="text-primary/20 font-bold text-4xl pointer-events-none select-none z-10">
            Viết tại đây
          </span>
        </div>

        <div className="flex items-center justify-between">
          <div className="flex gap-2">
            <button className="px-5 py-2.5 bg-hover-bg text-secondary font-semibold text-sm rounded-full hover:bg-outline/50 transition-colors">
              Xóa
            </button>
            <button className="px-5 py-2.5 bg-hover-bg text-secondary font-semibold text-sm rounded-full hover:bg-outline/50 transition-colors">
              Hoàn tác
            </button>
          </div>
          <button className="px-6 py-2.5 bg-primary text-white font-bold text-sm rounded-full hover:opacity-90 transition-opacity">
            Kiểm tra nét chữ
          </button>
        </div>
      </div>
    </div>
  );
}
