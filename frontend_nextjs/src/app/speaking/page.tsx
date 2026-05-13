'use client';

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
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * (bitDepth / 8), true);
  view.setUint16(32, bitDepth / 8, true);
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

export default function SpeakingPage() {
  const queue = useSmartQueue();

  // ── Local State ──
  const [language, setLanguage] = useState<'en' | 'zh'>('en');
  const [targetText, setTargetText] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [activeStream, setActiveStream] = useState<MediaStream | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // ── Recording ──
  const startRecording = useCallback(async () => {
    try {
      queue.reset();
      setAudioBlob(null);
      chunksRef.current = [];

      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      setActiveStream(stream);

      const recorder = new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      recorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        setActiveStream(null);

        const webmBlob = new Blob(chunksRef.current, { type: 'audio/webm' });

        try {
          const arrayBuffer = await webmBlob.arrayBuffer();
          const ctx = new (window.AudioContext || (window as any).webkitAudioContext)();
          const decoded = await ctx.decodeAudioData(arrayBuffer);
          const wavBlob = audioBufferToWav(decoded);
          setAudioBlob(wavBlob);
        } catch {
          setAudioBlob(webmBlob);
        }
      };

      recorder.start();
      setIsRecording(true);
    } catch {
      alert('Không thể truy cập microphone. Vui lòng kiểm tra quyền truy cập.');
    }
  }, [queue]);

  const stopRecording = useCallback(() => {
    mediaRecorderRef.current?.stop();
    setIsRecording(false);
  }, []);

  // ── File Upload ──
  const handleFileUpload = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      queue.reset();
      setAudioBlob(file);
    }
  }, [queue]);

  // ── Submit ──
  const handleSubmit = useCallback(async () => {
    if (!audioBlob) return;
    await queue.submit(audioBlob, language, targetText || undefined);
  }, [audioBlob, language, targetText, queue]);

  const isIdle = queue.phase === 'idle';
  const isBusy = queue.phase !== 'idle' && queue.phase !== 'completed' && queue.phase !== 'error';
  const showResult = queue.phase === 'completed' && queue.resultData;

  return (
    <div className="flex-1 overflow-y-auto w-full p-8 pb-16">
      <div className="max-w-[800px] mx-auto space-y-6">

        {/* ── Header ── */}
        <div className="text-center mb-2">
          <h1 className="text-3xl font-bold text-primary">Luyện Phát Âm AI</h1>
          <p className="text-secondary mt-1">
            Ghi âm hoặc tải file — AI chấm điểm từng từ trong 5-10 giây
          </p>
        </div>

        {/* ── Language Toggle ── */}
        <div className="flex justify-center">
          <div className="inline-flex bg-hover-bg rounded-full p-1 border border-outline">
            <button
              id="lang-en"
              type="button"
              onClick={() => setLanguage('en')}
              className={`px-5 py-2 rounded-full text-sm font-semibold transition-all ${
                language === 'en'
                  ? 'bg-primary text-white shadow-sm'
                  : 'text-secondary hover:text-primary'
              }`}
            >
              🇬🇧 English
            </button>
            <button
              id="lang-zh"
              type="button"
              onClick={() => setLanguage('zh')}
              className={`px-5 py-2 rounded-full text-sm font-semibold transition-all ${
                language === 'zh'
                  ? 'bg-primary text-white shadow-sm'
                  : 'text-secondary hover:text-primary'
              }`}
            >
              🇨🇳 中文
            </button>
          </div>
        </div>

        {/* ── Main Card ── */}
        <div className="bg-surface border border-outline rounded-[1.5rem] p-8 shadow-sm space-y-6">

          {/* Target Text */}
          <div>
            <label
              htmlFor="target-text"
              className="block text-sm font-semibold text-primary mb-2"
            >
              {language === 'en' ? 'Câu mẫu' : '目标文本'}
              <span className="font-normal text-secondary ml-2">
                (để trống = chế độ tự do)
              </span>
            </label>
            <textarea
              id="target-text"
              rows={3}
              value={targetText}
              onChange={(e) => setTargetText(e.target.value)}
              disabled={isBusy}
              placeholder={
                language === 'en'
                  ? 'e.g. The quick brown fox jumps over the lazy dog'
                  : '例如：今天天气很好，我想出去散步。'
              }
              className="w-full rounded-xl border border-outline bg-hover-bg px-4 py-3 text-sm text-primary
                         placeholder:text-secondary/50 focus:outline-none focus:ring-2 focus:ring-[var(--accent-gradient-start)]
                         focus:border-transparent resize-none transition-shadow disabled:opacity-50"
            />
            <p className="mt-1.5 text-xs text-secondary">
              {targetText.trim()
                ? `📖 Chế độ Read-Aloud — Chấm điểm GOP từng ${language === 'zh' ? 'ký tự' : 'từ'}`
                : '🎤 Chế độ tự do — Nhận diện giọng nói + điểm lưu loát'}
            </p>
          </div>

          {/* Waveform */}
          <AudioWaveform
            isRecording={isRecording}
            stream={activeStream}
            height={64}
          />

          {/* Recording & Upload Controls */}
          <div className="flex flex-col sm:flex-row gap-3">
            {/* Record button */}
            <button
              id="record-btn"
              type="button"
              onClick={isRecording ? stopRecording : startRecording}
              disabled={isBusy}
              className={`relative flex-1 flex items-center justify-center gap-2.5 px-4 py-3.5 rounded-xl font-semibold text-sm
                         transition-all focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:opacity-40
                         ${isRecording
                  ? 'bg-red-500 hover:bg-red-600 text-white focus:ring-red-400'
                  : 'bg-gradient-to-r from-[var(--accent-gradient-start)] to-[var(--accent-gradient-end)] text-white hover:opacity-90 focus:ring-[var(--accent-gradient-start)] shadow-md hover:shadow-lg'
                }`}
            >
              {isRecording && <span className="absolute inset-0 rounded-xl animate-pulse-ring text-red-300" />}
              {isRecording ? (
                <>
                  <span className="w-3.5 h-3.5 bg-white rounded-sm" />
                  Dừng ghi âm
                </>
              ) : (
                <>
                  <span className="material-symbols-outlined text-lg">mic</span>
                  Ghi âm
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
              id="upload-btn"
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={isBusy || isRecording}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-3.5 rounded-xl font-semibold text-sm
                         bg-hover-bg hover:bg-outline/50 text-secondary transition-all focus:outline-none
                         focus:ring-2 focus:ring-offset-2 focus:ring-primary/30 disabled:opacity-40
                         border border-outline"
            >
              <span className="material-symbols-outlined text-lg">upload_file</span>
              Tải file lên
            </button>
          </div>

          {/* Audio Ready Indicator */}
          {audioBlob && isIdle && (
            <div className="flex items-center gap-2 animate-fade-in">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              <p className="text-xs font-medium text-emerald-600">
                Sẵn sàng — {(audioBlob.size / 1024).toFixed(1)} KB
              </p>
            </div>
          )}

          {/* Submit Button */}
          {isIdle && (
            <button
              id="submit-btn"
              type="button"
              onClick={handleSubmit}
              disabled={!audioBlob}
              className="w-full py-3.5 rounded-xl font-bold text-sm transition-all focus:outline-none
                         focus:ring-2 focus:ring-offset-2 focus:ring-[var(--accent-gradient-start)] disabled:opacity-30
                         disabled:cursor-not-allowed bg-primary hover:bg-primary/90 text-white shadow-md
                         hover:shadow-lg active:scale-[0.98]"
            >
              {targetText.trim()
                ? `Chấm điểm Read-Aloud (${language === 'en' ? 'EN' : 'ZH'})`
                : `Chấm điểm tự do (${language === 'en' ? 'EN' : 'ZH'})`}
            </button>
          )}
        </div>

        {/* ── Smart Queue Status ── */}
        <SmartQueueStatus
          phase={queue.phase}
          queuePosition={queue.queuePosition}
          estimatedWait={queue.estimatedWait}
        />

        {/* ── Error Display ── */}
        {queue.phase === 'error' && queue.errorMessage && (
          <div className="animate-slide-up rounded-2xl border border-red-200 bg-red-50 p-5">
            <div className="flex items-start gap-3">
              <span className="material-symbols-outlined text-red-500 text-xl mt-0.5">error</span>
              <div>
                <p className="text-sm font-semibold text-red-700">Đã xảy ra lỗi</p>
                <p className="text-sm text-red-600 mt-1">{queue.errorMessage}</p>
              </div>
            </div>
            <button
              onClick={queue.reset}
              className="mt-3 text-xs font-semibold text-red-700 hover:text-red-800 underline"
            >
              Thử lại
            </button>
          </div>
        )}

        {/* ── Score Result ── */}
        {showResult && queue.resultData && (
          <div>
            <ScoreDisplay result={queue.resultData} overallScore={queue.score} />
            <div className="mt-4 flex justify-center">
              <button
                onClick={() => {
                  queue.reset();
                  setAudioBlob(null);
                }}
                className="px-6 py-2.5 bg-hover-bg hover:bg-outline/50 text-primary font-semibold text-sm rounded-full
                           transition-colors border border-outline"
              >
                🎤 Ghi âm mới
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
