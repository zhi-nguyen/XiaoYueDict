"use client";

import React from 'react';
import Link from 'next/link';

export default function HomePage() {
  return (
    <div className="flex-1 overflow-y-auto w-full p-8 pb-16">
      <div className="max-w-[1280px] mx-auto space-y-8">

        {/* ── Welcome Banner ── */}
        <div className="relative overflow-hidden rounded-[1.5rem] bg-gradient-to-br from-[var(--accent-gradient-start)] to-[var(--accent-gradient-end)] p-8 text-white shadow-lg">
          <div className="relative z-10">
            <h1 className="text-3xl font-bold mb-2">Chào mừng trở lại! 👋</h1>
            <p className="text-white/80 text-lg">
              Hãy tiếp tục hành trình học tập của bạn với XiaoYueDict
            </p>
            <div className="flex gap-3 mt-6">
              <Link
                href="/speaking"
                className="inline-flex items-center gap-2 px-6 py-3 bg-white text-[var(--accent-gradient-start)] font-bold rounded-full hover:bg-white/90 transition-colors shadow-md text-sm"
              >
                <span className="material-symbols-outlined text-lg">mic</span>
                Luyện phát âm
              </Link>
              <Link
                href="/study"
                className="inline-flex items-center gap-2 px-6 py-3 bg-white/15 text-white font-semibold rounded-full hover:bg-white/25 transition-colors border border-white/20 text-sm"
              >
                <span className="material-symbols-outlined text-lg">book</span>
                Tra từ &amp; Học
              </Link>
            </div>
          </div>
          {/* Decorative circles */}
          <div className="absolute -top-10 -right-10 w-40 h-40 rounded-full bg-white/10" />
          <div className="absolute -bottom-6 -right-4 w-24 h-24 rounded-full bg-white/5" />
        </div>

        {/* ── Stats Grid ── */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="bg-surface border border-outline rounded-[1.5rem] p-6 shadow-sm card-hover">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-xl bg-emerald-50 flex items-center justify-center">
                <span className="material-symbols-outlined text-emerald-600 text-[20px]">trending_up</span>
              </div>
              <h3 className="font-bold text-lg text-primary">Tiến độ hôm nay</h3>
            </div>
            <p className="text-3xl font-black text-primary">
              15<span className="text-lg font-medium text-secondary">/20 từ</span>
            </p>
            <div className="mt-3 h-2 bg-hover-bg rounded-full overflow-hidden">
              <div className="h-full bg-emerald-500 rounded-full transition-all duration-500" style={{ width: '75%' }} />
            </div>
            <p className="text-xs text-secondary mt-2">Còn 5 từ nữa là hoàn thành mục tiêu!</p>
          </div>

          <div className="bg-surface border border-outline rounded-[1.5rem] p-6 shadow-sm card-hover">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-xl bg-orange-50 flex items-center justify-center">
                <span className="material-symbols-outlined text-orange filled text-[20px]">local_fire_department</span>
              </div>
              <h3 className="font-bold text-lg text-primary">Chuỗi học tập</h3>
            </div>
            <p className="text-3xl font-black text-primary">
              15<span className="text-lg font-medium text-secondary"> ngày</span>
            </p>
            <div className="flex gap-1 mt-3">
              {[...Array(7)].map((_, i) => (
                <div key={i} className={`flex-1 h-2 rounded-full ${i < 6 ? 'bg-orange' : 'bg-hover-bg'}`} />
              ))}
            </div>
            <p className="text-xs text-secondary mt-2">Chuỗi dài nhất: 22 ngày 🏆</p>
          </div>

          <div className="bg-surface border border-outline rounded-[1.5rem] p-6 shadow-sm card-hover">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-xl bg-blue-50 flex items-center justify-center">
                <span className="material-symbols-outlined text-blue-600 text-[20px]">school</span>
              </div>
              <h3 className="font-bold text-lg text-primary">Gợi ý bài tập</h3>
            </div>
            <p className="text-secondary text-sm mb-3">Ôn tập HSK 3 — Phần thi nghe</p>
            <Link
              href="/exam"
              className="inline-flex items-center gap-1 text-sm font-semibold text-primary hover:underline"
            >
              Bắt đầu ôn tập
              <span className="material-symbols-outlined text-[16px]">arrow_forward</span>
            </Link>
          </div>
        </div>

        {/* ── Quick Actions ── */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <Link
            href="/speaking"
            className="group bg-surface border border-outline rounded-[1.5rem] p-6 shadow-sm card-hover flex items-center gap-5"
          >
            <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-[var(--accent-gradient-start)] to-[var(--accent-gradient-end)] flex items-center justify-center text-white shadow-md group-hover:scale-105 transition-transform">
              <span className="material-symbols-outlined text-[28px]">record_voice_over</span>
            </div>
            <div>
              <h3 className="font-bold text-lg text-primary">Luyện Phát Âm AI</h3>
              <p className="text-secondary text-sm mt-0.5">Ghi âm và nhận điểm từng từ trong 5 giây</p>
            </div>
          </Link>

          <Link
            href="/writing"
            className="group bg-surface border border-outline rounded-[1.5rem] p-6 shadow-sm card-hover flex items-center gap-5"
          >
            <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center text-white shadow-md group-hover:scale-105 transition-transform">
              <span className="material-symbols-outlined text-[28px]">edit_note</span>
            </div>
            <div>
              <h3 className="font-bold text-lg text-primary">Luyện Viết AI</h3>
              <p className="text-secondary text-sm mt-0.5">Viết văn và nhờ AI chấm chữa ngữ pháp</p>
            </div>
          </Link>
        </div>
      </div>
    </div>
  );
}
