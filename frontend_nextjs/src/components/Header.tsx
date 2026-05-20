"use client";

import React from 'react';
import { useLanguage } from '@/context/LanguageContext';

export default function Header() {
  const { language, setLanguage } = useLanguage();

  return (
    <header className="h-[72px] bg-surface border-b border-outline px-6 flex items-center justify-between shrink-0 top-0 sticky z-10">
      {/* Search Bar section */}
      <div className="flex items-center flex-1 max-w-[600px]">
        <div className="relative w-full">
          <span className="material-symbols-outlined absolute left-4 top-1/2 -translate-y-1/2 text-secondary text-xl">
            search
          </span>
          <input
            type="text"
            placeholder={language === 'zh' ? "Nhập từ cần tra (Trung - Việt)..." : "Nhập từ cần tra (Anh - Việt)..."}
            className="w-full pl-12 pr-4 py-2.5 bg-hover-bg rounded-full border border-transparent focus:border-sage focus:outline-none focus:ring-0 text-sm font-lexend text-primary placeholder:text-secondary"
          />
        </div>
      </div>

      {/* Right Actions section */}
      <div className="flex items-center space-x-4 ml-6">
        {/* Language Toggle */}
        <div className="flex bg-hover-bg rounded-full p-1 border border-outline mr-2 shrink-0">
          <button
            onClick={() => setLanguage('zh')}
            className={`px-3 py-1.5 rounded-full text-xs font-bold transition-all flex items-center gap-1 ${
              language === 'zh'
                ? 'bg-primary text-white shadow-sm'
                : 'text-secondary hover:text-primary'
            }`}
          >
            <span>🇨🇳</span>
            <span className="hidden sm:inline">Trung</span>
          </button>
          <button
            onClick={() => setLanguage('en')}
            className={`px-3 py-1.5 rounded-full text-xs font-bold transition-all flex items-center gap-1 ${
              language === 'en'
                ? 'bg-primary text-white shadow-sm'
                : 'text-secondary hover:text-primary'
            }`}
          >
            <span>🇬🇧</span>
            <span className="hidden sm:inline">Anh</span>
          </button>
        </div>

        <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-outline hover:bg-hover-bg cursor-pointer transition-colors">
          <span className="material-symbols-outlined text-orange text-[20px] filled">
            local_fire_department
          </span>
          <span className="font-semibold text-sm text-primary">15 Ngày</span>
        </div>

        <button className="w-10 h-10 flex items-center justify-center rounded-full hover:bg-hover-bg text-secondary relative">
          <span className="material-symbols-outlined">notifications</span>
          <span className="absolute top-2 right-2 w-2 h-2 rounded-full bg-red-500 border border-surface"></span>
        </button>

        <button className="w-10 h-10 rounded-full bg-primary flex items-center justify-center text-white font-bold tracking-tight shadow-sm hover:opacity-90">
          AD
        </button>
      </div>
    </header>
  );
}
