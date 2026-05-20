"use client";

import React from 'react';
import { useLanguage } from '@/context/LanguageContext';

export default function WritingPage() {
  const { language } = useLanguage();

  return (
    <div className="flex-1 overflow-y-auto w-full p-8 pb-16">
      <div className="max-w-[800px] mx-auto">
        <div className="bg-surface border border-outline rounded-[1.5rem] p-8 shadow-sm flex flex-col items-center">
          <div className="w-16 h-16 rounded-xl bg-hover-bg flex items-center justify-center text-primary mb-4">
            <span className="material-symbols-outlined text-[32px]">edit_note</span>
          </div>
          <h1 className="text-3xl font-bold text-primary mb-2">
            {language === 'zh' ? 'Luyện Viết Tiếng Trung AI' : 'Luyện Viết Tiếng Anh AI'}
          </h1>
          <p className="text-secondary text-center mb-8">
            {language === 'zh' 
              ? 'Luyện tập viết các đoạn văn tiếng Trung và nhờ AI chấm chữa ngữ pháp.' 
              : 'Luyện tập viết các đoạn văn tiếng Anh và nhờ AI chấm chữa ngữ pháp.'}
          </p>
          <textarea 
            className="w-full h-48 p-4 bg-hover-bg border border-outline rounded-xl mb-4 focus:outline-none focus:border-sage resize-none text-primary"
            placeholder={language === 'zh' ? "Nhập đoạn văn tiếng Trung của bạn vào đây..." : "Nhập đoạn văn tiếng Anh của bạn vào đây..."}
          ></textarea>
          <button className="px-8 py-3 bg-primary text-white font-bold rounded-full hover:opacity-90 transition-opacity self-end">
            Gửi để AI chấm
          </button>
        </div>
      </div>
    </div>
  );
}
