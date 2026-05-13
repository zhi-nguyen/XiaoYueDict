'use client';

import React, { useRef, useEffect, useCallback } from 'react';

interface AudioWaveformProps {
  /** Whether we are actively recording */
  isRecording: boolean;
  /** The MediaStream to visualize (from getUserMedia) */
  stream: MediaStream | null;
  /** Height of the waveform canvas */
  height?: number;
  /** Color of the waveform bars */
  color?: string;
}

/**
 * Real-time audio waveform visualization using the Web Audio API.
 * Renders animated frequency bars from a live MediaStream.
 */
export default function AudioWaveform({
  isRecording,
  stream,
  height = 64,
  color,
}: AudioWaveformProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animationRef = useRef<number>(0);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    const analyser = analyserRef.current;

    if (!canvas || !analyser) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);
    analyser.getByteFrequencyData(dataArray);

    const dpr = window.devicePixelRatio || 1;
    const width = canvas.clientWidth;
    const drawHeight = canvas.clientHeight;

    canvas.width = width * dpr;
    canvas.height = drawHeight * dpr;
    ctx.scale(dpr, dpr);

    ctx.clearRect(0, 0, width, drawHeight);

    // Draw bars
    const barCount = 40;
    const gap = 3;
    const barWidth = (width - gap * (barCount - 1)) / barCount;
    const step = Math.floor(bufferLength / barCount);

    const barColor = color || getComputedStyle(document.documentElement)
      .getPropertyValue('--accent-gradient-start').trim() || '#6366F1';

    for (let i = 0; i < barCount; i++) {
      const value = dataArray[i * step] / 255;
      const barHeight = Math.max(3, value * drawHeight * 0.85);

      const x = i * (barWidth + gap);
      const y = (drawHeight - barHeight) / 2;

      ctx.fillStyle = barColor;
      ctx.globalAlpha = 0.4 + value * 0.6;
      ctx.beginPath();
      ctx.roundRect(x, y, barWidth, barHeight, barWidth / 2);
      ctx.fill();
    }

    ctx.globalAlpha = 1;
    animationRef.current = requestAnimationFrame(draw);
  }, [color]);

  useEffect(() => {
    if (!isRecording || !stream) {
      // Draw idle state
      const canvas = canvasRef.current;
      if (canvas) {
        const ctx = canvas.getContext('2d');
        if (ctx) {
          const dpr = window.devicePixelRatio || 1;
          canvas.width = canvas.clientWidth * dpr;
          canvas.height = canvas.clientHeight * dpr;
          ctx.scale(dpr, dpr);
          ctx.clearRect(0, 0, canvas.clientWidth, canvas.clientHeight);

          // Draw subtle idle bars
          const barCount = 40;
          const gap = 3;
          const barWidth = (canvas.clientWidth - gap * (barCount - 1)) / barCount;

          for (let i = 0; i < barCount; i++) {
            const idleHeight = 3 + Math.sin(i * 0.5) * 2;
            const x = i * (barWidth + gap);
            const y = (canvas.clientHeight - idleHeight) / 2;

            ctx.fillStyle = getComputedStyle(document.documentElement)
              .getPropertyValue('--color-outline').trim() || '#E2E8F0';
            ctx.globalAlpha = 0.5;
            ctx.beginPath();
            ctx.roundRect(x, y, barWidth, idleHeight, barWidth / 2);
            ctx.fill();
          }
        }
      }
      return;
    }

    // Set up Web Audio API
    const audioContext = new (window.AudioContext || (window as any).webkitAudioContext)();
    audioContextRef.current = audioContext;

    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 256;
    analyser.smoothingTimeConstant = 0.7;
    analyserRef.current = analyser;

    const source = audioContext.createMediaStreamSource(stream);
    source.connect(analyser);

    // Start animation loop
    animationRef.current = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(animationRef.current);
      source.disconnect();
      audioContext.close();
    };
  }, [isRecording, stream, draw]);

  return (
    <div className="w-full rounded-xl bg-hover-bg border border-outline/30 overflow-hidden" style={{ height }}>
      <canvas
        ref={canvasRef}
        className="w-full h-full"
        style={{ display: 'block' }}
      />
    </div>
  );
}
