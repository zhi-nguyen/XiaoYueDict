"use client";

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { fetchExams } from '@/lib/api/exams';
import { Exam } from '@/types/exam';
import { getAllSavedExamIds, clearExamState } from '@/lib/examState';
import { useRouter } from 'next/navigation';

export default function ExamPage() {
  const router = useRouter();
  const [exams, setExams] = useState<Exam[]>([]);
  const [savedExamIds, setSavedExamIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadExams() {
      try {
        const data = await fetchExams();
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
  }, []);

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
        <h1 className="text-3xl font-bold text-primary mb-6">Luyện Thi HSK</h1>
        
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
