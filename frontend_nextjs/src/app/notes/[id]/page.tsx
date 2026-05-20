"use client";

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { fetchNotebook, fetchWords, createWord, deleteWord, updateNotebook, deleteNotebook } from '@/lib/api/notes';
import { Notebook, Word } from '@/types/note';

export default function NotebookDetailPage() {
  const params = useParams();
  const router = useRouter();
  const notebookId = parseInt(params.id as string, 10);

  const [notebook, setNotebook] = useState<Notebook | null>(null);
  const [words, setWords] = useState<Word[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [showAddModal, setShowAddModal] = useState(false);
  const [newVocab, setNewVocab] = useState('');
  const [newPinyin, setNewPinyin] = useState('');
  const [newMeaning, setNewMeaning] = useState('');
  const [newNotes, setNewNotes] = useState('');
  const [adding, setAdding] = useState(false);
  
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [editName, setEditName] = useState('');
  const [editDesc, setEditDesc] = useState('');
  
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    if (isNaN(notebookId)) {
      setError("ID Sổ tay không hợp lệ");
      setLoading(false);
      return;
    }
    loadData();
  }, [notebookId]);

  useEffect(() => {
    if (!isNaN(notebookId)) {
      const delayDebounceFn = setTimeout(() => {
        loadWords(searchQuery);
      }, 300);
      return () => clearTimeout(delayDebounceFn);
    }
  }, [searchQuery, notebookId]);

  async function loadData() {
    try {
      setLoading(true);
      const nb = await fetchNotebook(notebookId);
      setNotebook(nb);
      setEditName(nb.name);
      setEditDesc(nb.description || '');
      await loadWords('');
    } catch (err) {
      setError('Không thể tải dữ liệu sổ tay.');
    } finally {
      setLoading(false);
    }
  }

  async function loadWords(search: string) {
    try {
      const wds = await fetchWords(notebookId, search);
      setWords(wds);
    } catch (err) {
      console.error("Failed to load words");
    }
  }

  async function handleAddWord(e: React.FormEvent) {
    e.preventDefault();
    if (!newVocab.trim() || !newMeaning.trim()) return;
    try {
      setAdding(true);
      const newWord = await createWord(notebookId, {
        vocabulary: newVocab.trim(),
        pinyin: newPinyin.trim(),
        meaning: newMeaning.trim(),
        notes: newNotes.trim()
      });
      setWords([newWord, ...words]);
      setShowAddModal(false);
      setNewVocab('');
      setNewPinyin('');
      setNewMeaning('');
      setNewNotes('');
      // update count
      if (notebook) setNotebook({...notebook, word_count_annotated: (notebook.word_count_annotated || 0) + 1});
    } catch (err) {
      alert('Lỗi khi thêm từ vựng');
    } finally {
      setAdding(false);
    }
  }

  async function handleDeleteWord(wordId: number) {
    if (!confirm('Bạn có chắc muốn xóa từ này khỏi sổ tay?')) return;
    try {
      await deleteWord(notebookId, wordId);
      setWords(words.filter(w => w.id !== wordId));
      if (notebook) setNotebook({...notebook, word_count_annotated: Math.max(0, (notebook.word_count_annotated || 1) - 1)});
    } catch (err) {
      alert('Lỗi khi xóa từ vựng');
    }
  }

  async function handleUpdateNotebook(e: React.FormEvent) {
    e.preventDefault();
    try {
      const updated = await updateNotebook(notebookId, {
        name: editName.trim(),
        description: editDesc.trim(),
      });
      setNotebook({...notebook!, ...updated});
      setShowSettingsModal(false);
    } catch (err) {
      alert("Lỗi khi cập nhật");
    }
  }

  async function handleDeleteNotebook() {
    if (!confirm('Hành động này không thể hoàn tác. Bạn chắc chắn muốn xóa sổ tay này cùng với toàn bộ từ vựng bên trong?')) return;
    try {
      await deleteNotebook(notebookId);
      router.push('/notes');
    } catch (err) {
      alert("Lỗi khi xóa sổ tay");
    }
  }

  if (loading) {
    return (
      <div className="flex-1 flex justify-center items-center">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-primary"></div>
      </div>
    );
  }

  if (error || !notebook) {
    return (
      <div className="flex-1 p-8">
        <div className="bg-red-50 text-red-500 p-4 rounded-xl mb-6">
          {error || 'Sổ tay không tồn tại.'}
        </div>
        <Link href="/notes" className="text-primary hover:underline">&larr; Quay lại danh sách</Link>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col h-full bg-surface">
      {/* Header */}
      <div className="px-8 py-6 border-b border-outline flex items-center justify-between shrink-0 bg-white sticky top-0 z-10">
        <div className="flex items-center">
          <Link href="/notes" className="mr-4 p-2 hover:bg-hover-bg rounded-full text-secondary transition-colors">
            <span className="material-symbols-outlined">arrow_back</span>
          </Link>
          <div>
            <h1 className="text-2xl font-bold text-primary">{notebook.name}</h1>
            <p className="text-sm text-secondary">{notebook.description || 'Chưa có mô tả'} • {notebook.word_count_annotated || 0} từ vựng</p>
          </div>
        </div>
        <div className="flex gap-3">
          <button 
            onClick={() => setShowSettingsModal(true)}
            className="p-2.5 text-secondary border border-outline rounded-xl hover:bg-hover-bg transition-colors flex items-center justify-center"
            title="Cài đặt sổ tay"
          >
            <span className="material-symbols-outlined">settings</span>
          </button>
          <button 
            onClick={() => setShowAddModal(true)}
            className="bg-primary text-white px-5 py-2.5 rounded-xl font-bold hover:bg-primary-hover transition-colors flex items-center shadow-sm"
          >
            <span className="material-symbols-outlined mr-2">add</span>
            Thêm từ mới
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto w-full p-8 pb-16">
        <div className="max-w-[1000px] mx-auto">
          {/* Toolbar */}
          <div className="mb-6 flex">
            <div className="relative flex-1 max-w-md">
              <span className="material-symbols-outlined absolute left-4 top-1/2 -translate-y-1/2 text-secondary">search</span>
              <input 
                type="text" 
                placeholder="Tìm từ vựng, pinyin hoặc nghĩa..." 
                className="w-full pl-12 pr-4 py-3 bg-white border border-outline rounded-xl focus:outline-none focus:border-primary transition-colors shadow-sm"
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
              />
            </div>
          </div>

          {words.length === 0 ? (
            <div className="text-center py-20 text-secondary bg-white border border-outline rounded-2xl">
              <span className="material-symbols-outlined text-5xl mb-4 opacity-50">search_off</span>
              <p>{searchQuery ? "Không tìm thấy từ vựng nào phù hợp." : "Sổ tay trống. Hãy thêm từ vựng mới để bắt đầu học."}</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {words.map(word => (
                <div key={word.id} className="bg-white border border-outline rounded-2xl p-5 hover:border-primary/50 transition-colors group relative">
                  <button 
                    onClick={() => handleDeleteWord(word.id)}
                    className="absolute top-4 right-4 text-secondary hover:text-red-500 opacity-70 md:opacity-0 group-hover:opacity-100 transition-opacity"
                    title="Xóa từ"
                  >
                    <span className="material-symbols-outlined text-xl">delete</span>
                  </button>
                  <div className="flex items-start gap-4">
                    <div className="w-14 h-14 rounded-xl bg-primary/10 flex items-center justify-center text-primary text-2xl font-bold shrink-0 font-noto-sc">
                      {word.vocabulary.charAt(0)}
                    </div>
                    <div>
                      <div className="font-noto-sc text-2xl font-bold text-primary mb-1">{word.vocabulary}</div>
                      <div className="text-sm font-medium text-[#10b981] mb-2">{word.pinyin}</div>
                      <div className="text-base text-gray-800 font-medium">{word.meaning}</div>
                      {word.notes && (
                        <div className="mt-3 text-sm text-secondary bg-gray-50 p-2.5 rounded-lg border border-gray-100">
                          {word.notes}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Add Word Modal */}
      {showAddModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4 animate-in fade-in">
          <div className="bg-white rounded-2xl p-6 w-full max-w-lg shadow-xl">
            <h2 className="text-2xl font-bold text-primary mb-4">Thêm từ vựng mới</h2>
            <form onSubmit={handleAddWord}>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-secondary mb-1">Từ vựng (Tiếng Trung)</label>
                  <input 
                    type="text" 
                    value={newVocab}
                    onChange={e => setNewVocab(e.target.value)}
                    className="w-full border border-outline rounded-xl px-4 py-2.5 focus:outline-none focus:border-primary transition-colors font-noto-sc text-lg"
                    placeholder="VD: 学习"
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-secondary mb-1">Pinyin (Bính âm)</label>
                  <input 
                    type="text" 
                    value={newPinyin}
                    onChange={e => setNewPinyin(e.target.value)}
                    className="w-full border border-outline rounded-xl px-4 py-2.5 focus:outline-none focus:border-primary transition-colors"
                    placeholder="VD: xuéxí"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-secondary mb-1">Nghĩa</label>
                  <input 
                    type="text" 
                    value={newMeaning}
                    onChange={e => setNewMeaning(e.target.value)}
                    className="w-full border border-outline rounded-xl px-4 py-2.5 focus:outline-none focus:border-primary transition-colors"
                    placeholder="VD: Học tập"
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-secondary mb-1">Ghi chú (tùy chọn)</label>
                  <textarea 
                    value={newNotes}
                    onChange={e => setNewNotes(e.target.value)}
                    className="w-full border border-outline rounded-xl px-4 py-2.5 focus:outline-none focus:border-primary transition-colors min-h-[80px]"
                    placeholder="Ví dụ đặt câu, từ đồng nghĩa..."
                  />
                </div>
              </div>
              <div className="flex justify-end gap-3 mt-6">
                <button 
                  type="button" 
                  onClick={() => setShowAddModal(false)}
                  className="px-5 py-2.5 rounded-xl font-medium text-secondary hover:bg-hover-bg transition-colors"
                >
                  Hủy
                </button>
                <button 
                  type="submit" 
                  disabled={adding || !newVocab.trim() || !newMeaning.trim()}
                  className="bg-primary text-white px-5 py-2.5 rounded-xl font-bold hover:bg-primary-hover transition-colors disabled:opacity-50 flex items-center"
                >
                  {adding ? <span className="material-symbols-outlined animate-spin mr-2">progress_activity</span> : null}
                  Lưu từ vựng
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Settings Modal */}
      {showSettingsModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4 animate-in fade-in">
          <div className="bg-white rounded-2xl p-6 w-full max-w-md shadow-xl">
            <h2 className="text-2xl font-bold text-primary mb-4">Cài đặt sổ tay</h2>
            <form onSubmit={handleUpdateNotebook}>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-secondary mb-1">Tên sổ tay</label>
                  <input 
                    type="text" 
                    value={editName}
                    onChange={e => setEditName(e.target.value)}
                    className="w-full border border-outline rounded-xl px-4 py-2.5 focus:outline-none focus:border-primary transition-colors"
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-secondary mb-1">Mô tả</label>
                  <textarea 
                    value={editDesc}
                    onChange={e => setEditDesc(e.target.value)}
                    className="w-full border border-outline rounded-xl px-4 py-2.5 focus:outline-none focus:border-primary transition-colors min-h-[100px]"
                  />
                </div>
              </div>
              <div className="flex justify-between items-center mt-6">
                <button
                  type="button"
                  onClick={handleDeleteNotebook}
                  className="text-red-500 hover:bg-red-50 px-4 py-2 rounded-lg font-medium transition-colors"
                >
                  Xóa sổ tay
                </button>
                <div className="flex gap-2">
                  <button 
                    type="button" 
                    onClick={() => setShowSettingsModal(false)}
                    className="px-4 py-2 rounded-xl font-medium text-secondary hover:bg-hover-bg transition-colors"
                  >
                    Hủy
                  </button>
                  <button 
                    type="submit" 
                    disabled={!editName.trim()}
                    className="bg-primary text-white px-5 py-2 rounded-xl font-bold hover:bg-primary-hover transition-colors disabled:opacity-50"
                  >
                    Lưu thay đổi
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
