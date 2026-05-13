"use client";

import React from 'react';

export default function ExamPage() {
  return (
    <div className="flex-1 overflow-y-auto w-full p-8 pb-16">
      <div className="max-w-[1280px] mx-auto">
        <h1 className="text-3xl font-bold text-primary mb-6">Luyện Thi HSK</h1>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[1, 2, 3, 4, 5, 6].map(level => (
            <div key={level} className="bg-surface border border-outline rounded-[1.5rem] p-6 shadow-sm hover:border-outline-variant transition-colors cursor-pointer">
              <div className="w-16 h-16 rounded-xl bg-hover-bg flex items-center justify-center text-primary mb-4">
                <span className="font-bold text-xl">HSK {level}</span>
              </div>
              <h3 className="font-bold text-lg mb-2 text-primary">Đề thi mô phỏng HSK {level}</h3>
              <p className="text-secondary text-sm mb-4">Các bộ đề sát với thực tế, bao gồm nghe, đọc và viết.</p>
              <button className="text-primary font-bold text-sm hover:underline">Xem đề thi &rarr;</button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
