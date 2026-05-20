import { Exam } from '@/types/exam';

const API_BASE = process.env.NEXT_PUBLIC_GATEWAY_URL || 'http://localhost';

export async function fetchExams(level?: string, language?: string): Promise<Exam[]> {
  const params = new URLSearchParams();
  if (level) params.append('level', level);
  if (language) params.append('language', language);
  
  const queryStr = params.toString();
  const url = queryStr 
    ? `${API_BASE}/api/core/exams/?${queryStr}` 
    : `${API_BASE}/api/core/exams/`;
    
  const res = await fetch(url, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
    },
    // Exams list can be cached but let's revalidate every 60 seconds
    next: { revalidate: 60 },
  });

  if (!res.ok) {
    throw new Error('Failed to fetch exams');
  }

  return res.json();
}

export async function fetchExamDetails(examId: number): Promise<Exam> {
  const url = `${API_BASE}/api/core/exams/${examId}/full_exam/`;
  
  const res = await fetch(url, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
    },
    cache: 'no-store', // Real-time data for taking exam
  });

  if (!res.ok) {
    throw new Error('Failed to fetch exam details');
  }

  return res.json();
}
