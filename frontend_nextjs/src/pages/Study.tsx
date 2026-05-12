"use client";

import React from 'react';
import WordCard from '../components/WordCard';
import PracticeHub from '../components/PracticeHub';

export default function Study() {
  return (
    <main className="flex-1 overflow-y-auto w-full p-8 pb-16">
      <div className="max-w-[1280px] mx-auto grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
        {/* Left Column (Word Profile) : usually 5 cols wide */}
        <div className="lg:col-span-5 h-full relative">
          <WordCard />
        </div>
        
        {/* Right Column (Practice Activities) : usually 7 cols wide */}
        <div className="lg:col-span-7 h-full">
          <PracticeHub />
        </div>
      </div>
    </main>
  );
}
