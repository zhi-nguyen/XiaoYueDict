"use client";

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

const navItems = [
  { href: '/', icon: 'home', label: 'Trang chủ' },
  { href: '/study', icon: 'book', label: 'Tra từ & Học tập' },
  { href: '/speaking', icon: 'mic', label: 'Luyện Nói AI' },
  { href: '/writing', icon: 'edit', label: 'Luyện Viết AI' },
  { href: '/exam', icon: 'emoji_events', label: 'Luyện Thi' },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-[260px] h-full bg-surface border-r border-outline flex flex-col shrink-0">
      {/* Toggle & Brand Section */}
      <div className="h-[72px] flex items-center px-5 shrink-0">
        <button className="p-2 rounded-full hover:bg-hover-bg text-primary transition-colors flex items-center justify-center">
          <span className="material-symbols-outlined">menu_open</span>
        </button>
        <div className="ml-3 font-lexend font-bold text-xl text-primary tracking-tight">
          XiaoYueDict
        </div>
      </div>

      {/* Main Navigation */}
      <nav className="flex-1 px-4 space-y-1 sidebar-scroll overflow-y-auto overflow-x-hidden pt-4">
        {navItems.map(item => {
          const isActive = pathname === item.href;
          return (
            <Link 
              key={item.href}
              href={item.href}
              className={`flex items-center h-12 px-3 rounded-full transition-colors ${isActive ? 'bg-primary text-white' : 'text-secondary hover:bg-hover-bg hover:text-primary'}`}
            >
              <span className={`material-symbols-outlined ${isActive ? 'filled' : ''} w-6 flex justify-center`}>{item.icon}</span>
              <span className="ml-3 font-medium text-[15px]">{item.label}</span>
            </Link>
          );
        })}

        {/* Divider */}
        <div className="my-6 border-t border-outline"></div>

        {/* Secondary Menu (Upcoming) */}
        <div className="space-y-1 opacity-50 px-3">
          <div className="flex items-center h-12 text-secondary/70">
            <span className="material-symbols-outlined w-6 flex justify-center">headphones</span>
            <div className="ml-3 flex flex-col justify-center">
              <span className="font-medium text-[15px] leading-tight">Luyện Nghe</span>
              <span className="text-[10px] font-bold uppercase tracking-wider">Sắp ra mắt</span>
            </div>
          </div>
          <div className="flex items-center h-12 text-secondary/70">
            <span className="material-symbols-outlined w-6 flex justify-center">videogame_asset</span>
            <div className="ml-3 flex flex-col justify-center">
              <span className="font-medium text-[15px] leading-tight">Mini Game</span>
              <span className="text-[10px] font-bold uppercase tracking-wider">Sắp ra mắt</span>
            </div>
          </div>
        </div>
      </nav>

      {/* Bottom Actions */}
      <div className="p-4 shrink-0 border-t border-outline">
        <Link href="#" className="flex items-center h-12 px-3 rounded-full text-secondary hover:bg-hover-bg hover:text-primary transition-colors">
          <span className="material-symbols-outlined w-6 flex justify-center">settings</span>
          <span className="ml-3 font-medium text-[15px]">Cài đặt</span>
        </Link>
      </div>
    </aside>
  );
}
