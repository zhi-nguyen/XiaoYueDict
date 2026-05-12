"use client";

import React from 'react';

export default function Home() {
  return (
    <div className="flex-1 overflow-y-auto w-full p-8 pb-16">
      <div className="max-w-[1280px] mx-auto">
        <h1 className="text-3xl font-bold text-primary mb-6">Trang chủ</h1>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <div className="bg-surface border border-outline rounded-[1.5rem] p-6 shadow-sm">
            <h3 className="font-bold text-xl mb-2 text-primary">Tiến độ hôm nay</h3>
            <p className="text-secondary">Đã học: 15/20 từ mới</p>
          </div>
          <div className="bg-surface border border-outline rounded-[1.5rem] p-6 shadow-sm">
            <h3 className="font-bold text-xl mb-2 text-primary">Chuỗi học tập</h3>
            <p className="text-secondary">Bạn đang có chuỗi 15 ngày! Cố lên!</p>
          </div>
          <div className="bg-surface border border-outline rounded-[1.5rem] p-6 shadow-sm">
            <h3 className="font-bold text-xl mb-2 text-primary">Gợi ý bài tập</h3>
            <p className="text-secondary">Ôn tập HSK 3 - Phần thi nghe</p>
          </div>
        </div>
      </div>
    </div>
  );
}
