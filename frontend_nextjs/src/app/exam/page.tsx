"use client";

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { fetchExams } from '@/lib/api/exams';
import { useLanguage } from '@/context/LanguageContext';
import { Exam } from '@/types/exam';
import { getAllSavedExamIds, clearExamState } from '@/lib/examState';
import { useRouter } from 'next/navigation';

export default function ExamPage() {
  const router = useRouter();
  const { language } = useLanguage();
  const [exams, setExams] = useState<Exam[]>([]);
  const [savedExamIds, setSavedExamIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Settings states
  const [showSettings, setShowSettings] = useState(false);
  const [speedRate, setSpeedRate] = useState(1.0);
  const [volume, setVolume] = useState(1.0);
  const dropdownRef = React.useRef<HTMLDivElement>(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(event: Event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setShowSettings(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("touchstart", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("touchstart", handleClickOutside);
    };
  }, []);

  useEffect(() => {
    async function loadExams() {
      setLoading(true);
      try {
        const data = await fetchExams(undefined, language);
        setExams(data);
      } catch (err) {
        setError('Không thể tải danh sách đề thi. Vui lòng thử lại sau.');
      } finally {
        setLoading(false);
      }
    }
    loadExams();
    
    // Load saved states
    setSavedExamIds(getAllSavedExamIds());

    // Load saved settings
    const savedSpeed = localStorage.getItem('exam_audio_speed');
    if (savedSpeed) setSpeedRate(parseFloat(savedSpeed));
    const savedVolume = localStorage.getItem('exam_audio_volume');
    if (savedVolume) setVolume(parseFloat(savedVolume));
  }, [language]);

  const handleSpeedChange = (speed: number) => {
    setSpeedRate(speed);
    localStorage.setItem('exam_audio_speed', speed.toString());
  };

  const handleVolumeChange = (vol: number) => {
    setVolume(vol);
    localStorage.setItem('exam_audio_volume', vol.toString());
  };

  const handleStartOver = (examId: number) => {
    clearExamState(examId);
    router.push(`/exam/take/${examId}`);
  };

  // Group exams by level
  const groupedExams = exams.reduce((acc, exam) => {
    const level = exam.level || 'Khác';
    if (!acc[level]) acc[level] = [];
    acc[level].push(exam);
    return acc;
  }, {} as Record<string, Exam[]>);

  const levels = Object.keys(groupedExams).sort();

  return (
    <div className="flex-1 overflow-y-auto w-full p-8 pb-16">
      <div className="max-w-[1280px] mx-auto">
        <div className="flex justify-between items-center mb-6 relative">
          <h1 className="text-3xl font-bold text-primary">
            {language === 'zh' ? 'Luyện Thi HSK' : 'Luyện Thi IELTS'}
          </h1>
          
          {/* Settings Dropdown Container */}
          <div className="relative" ref={dropdownRef}>
            <button 
              onClick={() => setShowSettings(!showSettings)}
              className="flex items-center gap-2 px-4 py-2.5 bg-surface border border-outline hover:bg-hover-bg rounded-xl font-bold text-primary transition-all shadow-sm"
            >
              <svg className="w-5 h-5 text-secondary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
              </svg>
              Cài Đặt
            </button>

            {showSettings && (
              <div className="absolute right-0 mt-2 w-72 bg-surface border border-outline rounded-2xl p-4 shadow-xl z-50 space-y-4 animate-in fade-in slide-in-from-top-2 duration-200">
                <h3 className="font-bold text-primary border-b pb-2 mb-2">
                  Cấu hình âm thanh
                </h3>
                
                {/* Speed rate control */}
                <div className="space-y-1">
                  <label className="text-xs font-bold text-secondary flex justify-between">
                    <span>Tốc độ phát (Speed):</span>
                    <span className="text-primary font-mono">{speedRate.toFixed(2)}x</span>
                  </label>
                  <div className="flex items-center gap-2">
                    <svg className="w-4 h-4 text-secondary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                    <input 
                      type="range" 
                      min="0.5" 
                      max="2.0" 
                      step="0.05"
                      value={speedRate}
                      onChange={(e) => handleSpeedChange(parseFloat(e.target.value))}
                      className="flex-1 h-1.5 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-primary"
                    />
                  </div>
                </div>

                {/* Volume control */}
                <div className="space-y-1">
                  <label className="text-xs font-bold text-secondary flex justify-between">
                    <span>Âm lượng (Volume):</span>
                    <span className="text-primary font-mono">{Math.round(volume * 100)}%</span>
                  </label>
                  <div className="flex items-center gap-2">
                    <svg className="w-4 h-4 text-secondary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" />
                    </svg>
                    <input 
                      type="range" 
                      min="0" 
                      max="1" 
                      step="0.05"
                      value={volume}
                      onChange={(e) => handleVolumeChange(parseFloat(e.target.value))}
                      className="flex-1 h-1.5 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-primary"
                    />
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
        
        {loading && (
          <div className="flex justify-center items-center py-20">
            <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-primary"></div>
          </div>
        )}
        
        {error && (
          <div className="bg-red-50 text-red-500 p-4 rounded-xl mb-6">
            {error}
          </div>
        )}

        {!loading && !error && levels.length === 0 && (
          <div className="text-center py-20 text-secondary">
            Chưa có đề thi nào trong hệ thống.
          </div>
        )}

        {!loading && !error && levels.map(level => (
          <div key={level} className="mb-12">
            <h2 className="text-2xl font-bold text-primary mb-6 border-b pb-2">{level}</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {groupedExams[level].map(exam => (
                <div key={exam.id} className="bg-surface border border-outline rounded-[1.5rem] p-6 shadow-sm hover:border-outline-variant transition-colors flex flex-col">
                  <div className="w-16 h-16 rounded-xl bg-hover-bg flex items-center justify-center text-primary mb-4">
                    <span className="font-bold text-xl">{exam.level}</span>
                  </div>
                  <h3 className="font-bold text-lg mb-2 text-primary">{exam.exam_name}</h3>
                  <div className="text-secondary text-sm mb-4 flex-1 space-y-1">
                    <p>Thời gian: {exam.total_time_minutes} phút</p>
                    <p>Số câu hỏi: {exam.total_questions} câu</p>
                    <p>Điểm đạt: {exam.passing_score}/{exam.total_score}</p>
                  </div>
                  
                  <div className="mt-auto flex flex-col gap-2">
                    {savedExamIds.includes(exam.id.toString()) ? (
                      <>
                        <Link href={`/exam/take/${exam.id}`} className="block text-center bg-green-600 text-white font-bold py-3 rounded-xl hover:bg-green-700 transition-colors shadow-sm">
                          Tiếp tục làm bài
                        </Link>
                        <button 
                          onClick={() => handleStartOver(exam.id)}
                          className="block text-center w-full bg-white text-primary border border-primary font-bold py-3 rounded-xl hover:bg-primary/5 transition-colors"
                        >
                          Làm lại từ đầu
                        </button>
                      </>
                    ) : (
                      <Link href={`/exam/take/${exam.id}`} className="block text-center bg-primary text-white font-bold py-3 rounded-xl hover:bg-primary-hover transition-colors shadow-sm">
                        Bắt đầu làm bài
                      </Link>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
