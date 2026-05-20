"use client";

import React from 'react';
import { useLanguage } from '@/context/LanguageContext';

export default function WordCard() {
  const { language } = useLanguage();

  return (
    <div className="bg-surface border border-outline rounded-[1.5rem] p-8 sticky top-6 shadow-sm">
      {language === 'zh' ? (
        <>
          <div className="flex justify-between items-start mb-6">
            <div>
              <h1 className="text-[3.5rem] leading-none font-bold text-primary mb-2 flex items-baseline gap-3">
                学 <span className="text-3xl font-bold">(Xué)</span>
              </h1>
              <p className="text-xl text-secondary font-medium">xué - Động từ</p>
            </div>
            <button className="w-12 h-12 bg-primary text-white rounded-full flex items-center justify-center hover:opacity-90 transition-opacity">
              <span className="material-symbols-outlined text-2xl">volume_up</span>
            </button>
          </div>

          <div className="mb-8">
            <h2 className="text-[12px] font-bold uppercase tracking-wider text-secondary mb-3">
              Nghĩa của từ
            </h2>
            <p className="text-2xl text-primary font-semibold">
              Học, học tập
            </p>
          </div>

          <div className="space-y-4">
            <h2 className="text-[12px] font-bold uppercase tracking-wider text-secondary mb-2">
              Ví dụ sử dụng
            </h2>
            
            <div className="space-y-3">
              <div className="p-4 bg-hover-bg rounded-xl border border-outline/50">
                <p className="text-lg font-medium text-primary mb-1">他在大学学习法律。</p>
                <p className="text-secondary text-sm">Anh ấy đang học luật tại trường đại học.</p>
              </div>
              <div className="p-4 bg-hover-bg rounded-xl border border-outline/50">
                <p className="text-lg font-medium text-primary mb-1">活到老，学到老。</p>
                <p className="text-secondary text-sm">Học, học nữa, học mãi (Sống đến già, học đến già).</p>
              </div>
            </div>
          </div>
        </>
      ) : (
        <>
          <div className="flex justify-between items-start mb-6">
            <div>
              <h1 className="text-[3.5rem] leading-none font-bold text-primary mb-2 flex items-baseline gap-3">
                Learn
              </h1>
              <p className="text-xl text-secondary font-medium">/lɜːn/ - Động từ</p>
            </div>
            <button className="w-12 h-12 bg-primary text-white rounded-full flex items-center justify-center hover:opacity-90 transition-opacity">
              <span className="material-symbols-outlined text-2xl">volume_up</span>
            </button>
          </div>

          <div className="mb-8">
            <h2 className="text-[12px] font-bold uppercase tracking-wider text-secondary mb-3">
              Nghĩa của từ
            </h2>
            <p className="text-2xl text-primary font-semibold">
              Học, học hỏi, nghiên cứu
            </p>
          </div>

          <div className="space-y-4">
            <h2 className="text-[12px] font-bold uppercase tracking-wider text-secondary mb-2">
              Ví dụ sử dụng
            </h2>
            
            <div className="space-y-3">
              <div className="p-4 bg-hover-bg rounded-xl border border-outline/50">
                <p className="text-lg font-medium text-primary mb-1">He is learning English at university.</p>
                <p className="text-secondary text-sm">Anh ấy đang học tiếng Anh tại trường đại học.</p>
              </div>
              <div className="p-4 bg-hover-bg rounded-xl border border-outline/50">
                <p className="text-lg font-medium text-primary mb-1">Live and learn.</p>
                <p className="text-secondary text-sm">Sống và học hỏi (Học từ thực tế cuộc sống).</p>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
