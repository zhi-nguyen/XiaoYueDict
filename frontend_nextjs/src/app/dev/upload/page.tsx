"use client";

import React, { useState } from 'react';

const GATEWAY_URL = process.env.NEXT_PUBLIC_GATEWAY_URL || 'http://localhost';

export default function DevUploadPage() {
  const [examJson, setExamJson] = useState<File | null>(null);
  const [audioFile, setAudioFile] = useState<File | null>(null);
  const [imageMapping, setImageMapping] = useState<File | null>(null);
  const [images, setImages] = useState<File[]>([]);
  const [folderName, setFolderName] = useState<string>('');
  
  const [apiUrl, setApiUrl] = useState<string>(GATEWAY_URL);
  
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!examJson) {
      setError("Vui lòng chọn file JSON đề thi.");
      return;
    }

    setUploading(true);
    setError(null);
    setResult(null);

    const formData = new FormData();
    formData.append('exam_json', examJson);
    if (audioFile) formData.append('audio_file', audioFile);
    if (imageMapping) formData.append('image_mapping', imageMapping);
    
    if (images && images.length > 0) {
      for (let i = 0; i < images.length; i++) {
        formData.append('images', images[i]);
      }
    }

    try {
      const res = await fetch(`${apiUrl}/api/core/exams/upload_full_exam/`, {
        method: 'POST',
        body: formData,
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.error || 'Lỗi server khi upload');
      }

      setResult(data);
    } catch (err: any) {
      setError(err.message || 'Lỗi kết nối tới server.');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto w-full p-8 pb-16">
      <div className="max-w-[800px] mx-auto bg-surface border border-outline rounded-[1.5rem] p-8 shadow-sm">
        <h1 className="text-3xl font-bold text-primary mb-6 border-b pb-4">🛠 Dev: Upload Đề Thi</h1>
        
        <form onSubmit={handleUpload} className="space-y-6">
          {/* API URL Config */}
          <div className="bg-gray-50 p-4 rounded-xl border border-gray-200">
            <label className="block text-primary font-bold mb-2">
              API Gateway URL
              <span className="text-sm font-normal text-secondary ml-2">(Sửa thành http://127.0.0.1 nếu bị lỗi ALPN/localhost)</span>
            </label>
            <input 
              type="text" 
              value={apiUrl}
              onChange={(e) => setApiUrl(e.target.value)}
              className="w-full border border-outline-variant p-2 rounded-xl"
            />
          </div>

          {/* Single Folder Upload */}
          <div>
            <label className="block text-primary font-bold mb-2">
              Thư mục Đề thi <span className="text-red-500">*</span>
              <span className="text-sm font-normal text-secondary ml-2">(Chọn thư mục dạng HSK1_NEW_UUID_001)</span>
            </label>
            <input 
              type="file" 
              {...{ webkitdirectory: "", directory: "" } as any}
              multiple
              onChange={(e) => {
                const files = e.target.files;
                if (!files || files.length === 0) return;
                
                let tempExamJson: File | null = null;
                let tempAudioFile: File | null = null;
                let tempImageMapping: File | null = null;
                const tempImages: File[] = [];
                let detectedFolderName = '';

                for (let i = 0; i < files.length; i++) {
                  const file = files[i];
                  const path = file.webkitRelativePath || file.name;
                  
                  if (!detectedFolderName && path.includes('/')) {
                    detectedFolderName = path.split('/')[0];
                  }
                  
                  if ((path.includes('img_mapping') || path.includes('image_mapping')) && path.endsWith('.json')) {
                    tempImageMapping = file;
                  } else if (path.includes('test') && path.endsWith('.json')) {
                    tempExamJson = file;
                  } else if (path.includes('audio') && path.endsWith('.mp3')) {
                    tempAudioFile = file;
                  } else if ((path.includes('img') || path.includes('images')) && (path.endsWith('.png') || path.endsWith('.jpg') || path.endsWith('.jpeg'))) {
                    tempImages.push(file);
                  } else if (path.endsWith('.json') && !tempExamJson) {
                    tempExamJson = file; // Fallback
                  }
                }

                setExamJson(tempExamJson);
                setAudioFile(tempAudioFile);
                setImageMapping(tempImageMapping);
                setImages(tempImages);
                setFolderName(detectedFolderName || 'Đã chọn thư mục');
              }}
              className="w-full border border-outline-variant p-4 rounded-xl border-dashed bg-primary/5 hover:bg-primary/10 transition-colors cursor-pointer"
            />
          </div>

          {/* Detected Files Preview */}
          {folderName && (
            <div className="bg-blue-50 p-4 rounded-xl border border-blue-200">
              <h3 className="font-bold text-blue-900 mb-2">Đã quét thư mục: {folderName}</h3>
              <ul className="text-sm space-y-2 text-blue-800">
                <li className="flex items-center gap-2">
                  <span className={examJson ? "text-green-600" : "text-red-500"}>{examJson ? '✅' : '❌'}</span>
                  <strong>Exam JSON:</strong> {examJson ? examJson.name : 'Không tìm thấy'}
                </li>
                <li className="flex items-center gap-2">
                  <span className={audioFile ? "text-green-600" : "text-gray-400"}>{audioFile ? '✅' : '➖'}</span>
                  <strong>Audio:</strong> {audioFile ? audioFile.name : 'Không có'}
                </li>
                <li className="flex items-center gap-2">
                  <span className={imageMapping ? "text-green-600" : "text-gray-400"}>{imageMapping ? '✅' : '➖'}</span>
                  <strong>Image Mapping:</strong> {imageMapping ? imageMapping.name : 'Không có'}
                </li>
                <li className="flex items-center gap-2">
                  <span className={images.length > 0 ? "text-green-600" : "text-gray-400"}>{images.length > 0 ? '✅' : '➖'}</span>
                  <strong>Images:</strong> {images.length} file ảnh
                </li>
              </ul>
            </div>
          )}

          {error && (
            <div className="bg-red-50 text-red-700 p-4 rounded-xl border border-red-200">
              <span className="font-bold">Lỗi:</span> {error}
            </div>
          )}

          {result && (
            <div className="bg-green-50 text-green-700 p-4 rounded-xl border border-green-200">
              <span className="font-bold">Upload thành công!</span>
              <ul className="mt-2 text-sm list-disc list-inside">
                <li>Exam ID: {result.exam_id}</li>
                <li>Audio URL: {result.audio_url || 'Không có'}</li>
                <li>Số hình ảnh đã lưu: {result.images_uploaded}</li>
              </ul>
            </div>
          )}

          <button 
            type="submit" 
            disabled={uploading}
            className={`w-full font-bold text-white py-4 rounded-xl shadow-md transition-colors ${uploading ? 'bg-gray-400 cursor-not-allowed' : 'bg-primary hover:bg-primary-hover'}`}
          >
            {uploading ? 'Đang tải lên...' : 'Upload & Lưu vào Database'}
          </button>
        </form>
      </div>
    </div>
  );
}
