import { Notebook, Word } from '@/types/note';

const API_BASE = process.env.NEXT_PUBLIC_GATEWAY_URL || 'http://localhost';

export async function fetchNotebooks(): Promise<Notebook[]> {
  const url = `${API_BASE}/api/core/notes/notebooks/`;
  const res = await fetch(url, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
    cache: 'no-store',
  });
  if (!res.ok) throw new Error('Failed to fetch notebooks');
  return res.json();
}

export async function createNotebook(data: { name: string; description?: string }): Promise<Notebook> {
  const url = `${API_BASE}/api/core/notes/notebooks/`;
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to create notebook');
  return res.json();
}

export async function fetchNotebook(id: number): Promise<Notebook> {
  const url = `${API_BASE}/api/core/notes/notebooks/${id}/`;
  const res = await fetch(url, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
    cache: 'no-store',
  });
  if (!res.ok) throw new Error('Failed to fetch notebook details');
  return res.json();
}

export async function updateNotebook(id: number, data: { name?: string; description?: string }): Promise<Notebook> {
  const url = `${API_BASE}/api/core/notes/notebooks/${id}/`;
  const res = await fetch(url, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to update notebook');
  return res.json();
}

export async function deleteNotebook(id: number): Promise<void> {
  const url = `${API_BASE}/api/core/notes/notebooks/${id}/`;
  const res = await fetch(url, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error('Failed to delete notebook');
}

export async function fetchWords(notebookId: number, search?: string): Promise<Word[]> {
  let url = `${API_BASE}/api/core/notes/notebooks/${notebookId}/words/`;
  if (search) {
    url += `?search=${encodeURIComponent(search)}`;
  }
  const res = await fetch(url, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
    cache: 'no-store',
  });
  if (!res.ok) throw new Error('Failed to fetch words');
  return res.json();
}

export async function createWord(notebookId: number, data: { vocabulary: string; pinyin?: string; meaning: string; notes?: string }): Promise<Word> {
  const url = `${API_BASE}/api/core/notes/notebooks/${notebookId}/words/`;
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to create word');
  return res.json();
}

export async function updateWord(notebookId: number, wordId: number, data: { vocabulary?: string; pinyin?: string; meaning?: string; notes?: string }): Promise<Word> {
  const url = `${API_BASE}/api/core/notes/notebooks/${notebookId}/words/${wordId}/`;
  const res = await fetch(url, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to update word');
  return res.json();
}

export async function deleteWord(notebookId: number, wordId: number): Promise<void> {
  const url = `${API_BASE}/api/core/notes/notebooks/${notebookId}/words/${wordId}/`;
  const res = await fetch(url, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error('Failed to delete word');
}
