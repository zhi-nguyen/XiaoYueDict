export interface ExamState {
  version: string;
  answers: Record<string, string>;
  audioTime: number;
  timeRemaining: number;
  isSubmitted: boolean;
  lastSaved: number;
}

const getStorageKey = (examId: number | string) => `exam_state_${examId}`;

export const saveExamState = (examId: number | string, state: ExamState) => {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(getStorageKey(examId), JSON.stringify(state));
  } catch (error) {
    console.error('Failed to save exam state:', error);
  }
};

export const loadExamState = (examId: number | string): ExamState | null => {
  if (typeof window === 'undefined') return null;
  try {
    const data = localStorage.getItem(getStorageKey(examId));
    if (!data) return null;
    return JSON.parse(data) as ExamState;
  } catch (error) {
    console.error('Failed to load exam state:', error);
    return null;
  }
};

export const clearExamState = (examId: number | string) => {
  if (typeof window === 'undefined') return;
  try {
    localStorage.removeItem(getStorageKey(examId));
  } catch (error) {
    console.error('Failed to clear exam state:', error);
  }
};

export const getAllSavedExamIds = (): string[] => {
  if (typeof window === 'undefined') return [];
  const ids: string[] = [];
  for (let i = 0; i < localStorage.length; i++) {
    const key = localStorage.key(i);
    if (key && key.startsWith('exam_state_')) {
      ids.push(key.replace('exam_state_', ''));
    }
  }
  return ids;
};
