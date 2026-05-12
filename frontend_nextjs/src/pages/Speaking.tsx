"use client";

import React from 'react';

export default function Speaking() {
  return (
    <div className="flex-1 overflow-y-auto w-full p-8 pb-16">
      <div className="max-w-[800px] mx-auto">
        <div className="bg-surface border border-outline rounded-[1.5rem] p-8 shadow-sm flex flex-col items-center">
          <div className="w-16 h-16 rounded-xl bg-hover-bg flex items-center justify-center text-primary mb-4">
            <span className="material-symbols-outlined text-[32px]">record_voice_over</span>
          </div>
          <h1 className="text-3xl font-bold text-primary mb-2">Luyện Nói AI</h1>
          <p className="text-secondary text-center mb-8">Trò chuyện với AI để cải thiện kỹ năng phát âm và giao tiếp.</p>
          <button className="px-8 py-3 bg-primary text-white font-bold rounded-full hover:opacity-90 transition-opacity">
            Bắt đầu đoạn thoại mới
          </button>
        </div>
      </div>
    </div>
  );
}
