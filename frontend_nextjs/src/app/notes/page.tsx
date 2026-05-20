"use client";

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { fetchNotebooks, createNotebook, deleteNotebook } from '@/lib/api/notes';
import { Notebook } from '@/types/note';

export default function NotesPage() {
  const [notebooks, setNotebooks] = useState<Notebook[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newName, setNewName] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    loadNotebooks();
  }, []);

  async function loadNotebooks() {
    try {
      setLoading(true);
      const data = await fetchNotebooks();
      setNotebooks(data);
    } catch (err) {
      setError('Không thể tải danh sách sổ tay.');
    } finally {
      setLoading(false);
    }
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!newName.trim()) return;
    try {
      setCreating(true);
      const newNb = await createNotebook({ name: newName.trim(), description: newDesc.trim() });
      setNotebooks([newNb, ...notebooks]);
      setShowCreateModal(false);
      setNewName('');
      setNewDesc('');
    } catch (err) {
      alert('Lỗi khi tạo sổ tay');
    } finally {
      setCreating(false);
    }
  }

  async function handleDeleteNotebook(e: React.MouseEvent, id: number, name: string) {
    e.preventDefault();
    e.stopPropagation();
    if (!confirm(`Bạn có chắc chắn muốn xóa sổ tay "${name}"? Tất cả từ vựng bên trong sẽ bị xóa.`)) {
      return;
    }
    try {
      await deleteNotebook(id);
      setNotebooks(notebooks.filter(nb => nb.id !== id));
    } catch (err) {
      alert('Lỗi khi xóa sổ tay');
    }
  }

  return (
    <div className="flex-1 overflow-y-auto w-full p-8 pb-16">
      <div className="max-w-[1280px] mx-auto">
        <div className="flex justify-between items-center mb-6">
          <h1 className="text-3xl font-bold text-primary">Sổ Tay Của Tôi</h1>
          <button 
            onClick={() => setShowCreateModal(true)}
            className="bg-primary text-white px-5 py-2.5 rounded-xl font-bold hover:bg-primary-hover transition-colors flex items-center"
          >
            <span className="material-symbols-outlined mr-2">add</span>
            Tạo sổ mới
          </button>
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

        {!loading && !error && notebooks.length === 0 && (
          <div className="text-center py-20 text-secondary bg-surface border border-outline rounded-2xl">
            <span className="material-symbols-outlined text-5xl mb-4 opacity-50">menu_book</span>
            <p>Bạn chưa có sổ tay nào.</p>
            <button onClick={() => setShowCreateModal(true)} className="text-primary font-bold mt-2 hover:underline">
              Tạo sổ đầu tiên ngay
            </button>
          </div>
        )}

        {!loading && !error && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
            {notebooks.map(nb => (
              <div key={nb.id} className="relative group">
                <Link href={`/notes/${nb.id}`} className="bg-surface border border-outline rounded-[1.5rem] p-6 shadow-sm hover:border-outline-variant hover:shadow-md transition-all flex flex-col cursor-pointer h-full">
                  <div className="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center text-primary mb-4 group-hover:scale-110 transition-transform">
                    <span className="material-symbols-outlined">menu_book</span>
                  </div>
                  <h3 className="font-bold text-xl mb-1 text-primary line-clamp-1 pr-6">{nb.name}</h3>
                  <p className="text-secondary text-sm mb-4 line-clamp-2 flex-1">
                    {nb.description || "Chưa có mô tả"}
                  </p>
                  <div className="mt-auto flex items-center text-sm font-medium text-primary/80 bg-primary/5 px-3 py-1.5 rounded-lg w-fit">
                    <span className="material-symbols-outlined text-[18px] mr-1">translate</span>
                    {nb.word_count_annotated || 0} từ vựng
                  </div>
                </Link>
                <button
                  onClick={(e) => handleDeleteNotebook(e, nb.id, nb.name)}
                  className="absolute top-4 right-4 p-2 text-secondary hover:text-red-500 hover:bg-red-50 rounded-xl transition-all opacity-70 md:opacity-0 group-hover:opacity-100 focus:opacity-100"
                  title="Xóa sổ tay"
                >
                  <span className="material-symbols-outlined text-[20px]">delete</span>
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Create Modal */}
        {showCreateModal && (
          <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4 animate-in fade-in">
            <div className="bg-white rounded-2xl p-6 w-full max-w-md shadow-xl">
              <h2 className="text-2xl font-bold text-primary mb-4">Tạo Sổ Tay Mới</h2>
              <form onSubmit={handleCreate}>
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-secondary mb-1">Tên sổ tay</label>
                    <input 
                      type="text" 
                      value={newName}
                      onChange={e => setNewName(e.target.value)}
                      className="w-full border border-outline rounded-xl px-4 py-2.5 focus:outline-none focus:border-primary transition-colors"
                      placeholder="VD: Từ vựng HSK 4..."
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-secondary mb-1">Mô tả (tùy chọn)</label>
                    <textarea 
                      value={newDesc}
                      onChange={e => setNewDesc(e.target.value)}
                      className="w-full border border-outline rounded-xl px-4 py-2.5 focus:outline-none focus:border-primary transition-colors min-h-[100px]"
                      placeholder="Ghi chú thêm về sổ tay này..."
                    />
                  </div>
                </div>
                <div className="flex justify-end gap-3 mt-6">
                  <button 
                    type="button" 
                    onClick={() => setShowCreateModal(false)}
                    className="px-5 py-2.5 rounded-xl font-medium text-secondary hover:bg-hover-bg transition-colors"
                  >
                    Hủy
                  </button>
                  <button 
                    type="submit" 
                    disabled={creating || !newName.trim()}
                    className="bg-primary text-white px-5 py-2.5 rounded-xl font-bold hover:bg-primary-hover transition-colors disabled:opacity-50 flex items-center"
                  >
                    {creating ? (
                      <span className="material-symbols-outlined animate-spin mr-2">progress_activity</span>
                    ) : null}
                    Tạo mới
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

      </div>
    </div>
  );
}
