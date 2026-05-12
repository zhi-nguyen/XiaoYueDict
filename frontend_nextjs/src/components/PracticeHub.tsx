"use client";

import React from 'react';

export default function PracticeHub() {
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
              <circle cx="60" cy="60" r="54" fill="transparent" stroke="var(--color-outline)" strokeWidth="6"></circle>
              {/* 92% of circumference approx 339 */}
              <circle cx="60" cy="60" r="54" fill="transparent" stroke="var(--color-tertiary)" strokeWidth="6" strokeDasharray="339" strokeDashoffset="27" strokeLinecap="round"></circle>
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-[28px] font-bold text-tertiary leading-none mb-1">92<span className="text-base">/100</span></span>
              <span className="text-[10px] font-bold text-secondary uppercase tracking-widest">Điểm số</span>
            </div>
          </div>

          {/* Waveform Visualization & Mic button */}
          <div className="flex-1 w-full flex flex-col items-center gap-6">
            <div className="w-full h-16 bg-hover-bg rounded-xl flex items-center justify-center px-4 overflow-hidden relative border border-outline/30">
              {/* Fake Waveform */}
              <div className="flex items-center gap-1.5 h-full opacity-60">
                <div className="w-1.5 bg-primary/40 h-[20%] rounded-full"></div>
                <div className="w-1.5 bg-primary/60 h-[40%] rounded-full"></div>
                <div className="w-1.5 bg-primary h-[80%] rounded-full"></div>
                <div className="w-1.5 bg-primary h-[50%] rounded-full"></div>
                <div className="w-1.5 bg-primary/80 h-[90%] rounded-full"></div>
                <div className="w-1.5 bg-primary h-[30%] rounded-full"></div>
                <div className="w-1.5 bg-primary h-[100%] rounded-full"></div>
                <div className="w-1.5 bg-primary/60 h-[60%] rounded-full"></div>
                <div className="w-1.5 bg-primary h-[70%] rounded-full"></div>
                <div className="w-1.5 bg-primary/40 h-[40%] rounded-full"></div>
              </div>
            </div>

            <button className="w-14 h-14 rounded-full bg-primary text-white flex items-center justify-center shadow-md hover:bg-primary/90 transition-colors">
              <span className="material-symbols-outlined text-[28px]">mic</span>
            </button>
          </div>
        </div>

        {/* Feedback Chips */}
        <div className="grid grid-cols-2 gap-4">
          <div className="p-4 bg-green-50/50 border border-green-100 rounded-xl flex items-center gap-3">
            <span className="material-symbols-outlined text-green-600 text-[20px]">check_circle</span>
            <span className="font-semibold text-sm text-green-800">Phát âm tốt</span>
          </div>
          <div className="p-4 bg-orange-50/50 border border-orange-100 rounded-xl flex items-center gap-3">
            <span className="material-symbols-outlined text-orange text-[20px]">info</span>
            <span className="font-semibold text-sm text-orange-800">Cần chú ý thanh điệu</span>
          </div>
        </div>
      </div>

      {/* Handwriting Practice Card */}
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
          {/* Simulated user drawing overlay */}
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
