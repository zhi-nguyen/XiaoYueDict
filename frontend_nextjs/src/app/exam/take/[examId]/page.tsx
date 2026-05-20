"use client";

import React, { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { fetchExamDetails } from '@/lib/api/exams';
import { Exam } from '@/types/exam';
import ConfirmModal from '@/components/ConfirmModal';
import { saveExamState, loadExamState, clearExamState, ExamState } from '@/lib/examState';

const GATEWAY_URL = process.env.NEXT_PUBLIC_GATEWAY_URL || 'http://localhost';

const getMediaUrl = (url: string) => {
  if (!url) return url;
  if (url.startsWith('http://') || url.startsWith('https://')) return url;
  if (url.startsWith('/')) return `${GATEWAY_URL}${url}`;
  return url;
};

const timeToSeconds = (timeStr: string | null | undefined): number | null => {
  if (!timeStr) return null;
  const parts = timeStr.split(':').map(parseFloat);
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
  if (parts.length === 2) return parts[0] * 60 + parts[1];
  return parts[0];
};

export default function ExamTakePage() {
  const params = useParams();
  const router = useRouter();
  const examId = parseInt(params.examId as string, 10);

  const [exam, setExam] = useState<Exam | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // answers[question_id] = option_id
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [isSubmitted, setIsSubmitted] = useState(false);
  const [score, setScore] = useState(0);

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

  // Load settings on mount
  useEffect(() => {
    const savedSpeed = localStorage.getItem('exam_audio_speed');
    if (savedSpeed) setSpeedRate(parseFloat(savedSpeed));
    const savedVolume = localStorage.getItem('exam_audio_volume');
    if (savedVolume) setVolume(parseFloat(savedVolume));
  }, []);

  // Apply settings when audio element is rendered
  useEffect(() => {
    if (!loading && exam) {
      const timer = setTimeout(() => {
        const savedSpeed = localStorage.getItem('exam_audio_speed');
        const savedVolume = localStorage.getItem('exam_audio_volume');
        const speed = savedSpeed ? parseFloat(savedSpeed) : 1.0;
        const vol = savedVolume ? parseFloat(savedVolume) : 1.0;

        if (audioRef.current) {
          audioRef.current.playbackRate = speed;
          audioRef.current.volume = vol;
        }
        if (segmentAudioRef.current) {
          segmentAudioRef.current.playbackRate = speed;
          segmentAudioRef.current.volume = vol;
        }
      }, 100);
      return () => clearTimeout(timer);
    }
  }, [loading, exam]);

  const handleSpeedChange = (speed: number) => {
    setSpeedRate(speed);
    localStorage.setItem('exam_audio_speed', speed.toString());
    if (audioRef.current) {
      audioRef.current.playbackRate = speed;
    }
    if (segmentAudioRef.current) {
      segmentAudioRef.current.playbackRate = speed;
    }
  };

  const handleVolumeChange = (vol: number) => {
    setVolume(vol);
    localStorage.setItem('exam_audio_volume', vol.toString());
    if (audioRef.current) {
      audioRef.current.volume = vol;
    }
    if (segmentAudioRef.current) {
      segmentAudioRef.current.volume = vol;
    }
  };

  // New state variables for persistence and timer
  const [timeRemaining, setTimeRemaining] = useState<number | null>(null);
  const audioRef = React.useRef<HTMLAudioElement | null>(null);
  const segmentAudioRef = React.useRef<HTMLAudioElement | null>(null);
  const activeSegmentEndTimeRef = React.useRef<number | null>(null);

  const [isMainAudioPlaying, setIsMainAudioPlaying] = useState(false);
  const [activeSegmentId, setActiveSegmentId] = useState<string | null>(null);
  const [mainAudioCurrentTime, setMainAudioCurrentTime] = useState(0);

  const [modalConfig, setModalConfig] = useState<{
    isOpen: boolean;
    title: string;
    message: string;
    confirmText?: string;
    isDestructive?: boolean;
    onConfirm: () => void;
  }>({
    isOpen: false,
    title: '',
    message: '',
    onConfirm: () => {},
  });

  useEffect(() => {
    async function loadExam() {
      try {
        const data = await fetchExamDetails(examId);
        setExam(data);

        // Load saved state
        const savedState = loadExamState(examId);
        if (savedState && !savedState.isSubmitted) {
          setAnswers(savedState.answers);
          setTimeRemaining(savedState.timeRemaining);
          if (audioRef.current && savedState.audioTime) {
            audioRef.current.currentTime = savedState.audioTime;
          }
        } else {
          setTimeRemaining(data.total_time_minutes * 60);
        }
      } catch (err) {
        setError('Không thể tải bài thi.');
      } finally {
        setLoading(false);
      }
    }
    if (examId) loadExam();
  }, [examId]);

  // Timer countdown
  useEffect(() => {
    if (isSubmitted || timeRemaining === null) return;

    const interval = setInterval(() => {
      setTimeRemaining(prev => {
        if (prev === null) return null;
        if (prev <= 1) return 0;
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(interval);
  }, [isSubmitted, timeRemaining === null]);

  // Auto-submit when time hits 0
  useEffect(() => {
    if (timeRemaining === 0 && !isSubmitted && exam) {
      handleFinalSubmit();
      setModalConfig({
        isOpen: true,
        title: 'Hết giờ!',
        message: 'Thời gian làm bài đã hết. Bài thi của bạn đã được tự động nộp.',
        confirmText: 'Đóng',
        onConfirm: () => setModalConfig(prev => ({ ...prev, isOpen: false })),
      });
    }
  }, [timeRemaining, isSubmitted, exam]);

  // Auto-save state
  useEffect(() => {
    if (!exam || isSubmitted) return;
    
    saveExamState(examId, {
      version: '0.1',
      answers,
      audioTime: audioRef.current?.currentTime || 0,
      timeRemaining: timeRemaining || (exam.total_time_minutes * 60),
      isSubmitted,
      lastSaved: Date.now()
    });
  }, [answers, timeRemaining, isSubmitted, examId, exam]);

  const handleOptionSelect = (questionId: string, optionId: string) => {
    if (isSubmitted) return;
    setAnswers(prev => ({ ...prev, [questionId]: optionId }));
  };

  const handleFinalSubmit = () => {
    if (!exam || !exam.sections) return;

    let totalScore = 0;
    exam.sections.forEach(sec => {
      sec.questions.forEach(q => {
        if (answers[q.question_id] === q.correct_answer) {
          totalScore += q.points;
        }
      });
    });

    setScore(totalScore);
    setIsSubmitted(true);
    window.scrollTo(0, 0);

    saveExamState(examId, {
      version: '0.1',
      answers,
      audioTime: audioRef.current?.currentTime || 0,
      timeRemaining: timeRemaining || 0,
      isSubmitted: true,
      lastSaved: Date.now()
    });
  };

  const handleSubmit = () => {
    setModalConfig({
      isOpen: true,
      title: 'Nộp bài',
      message: 'Bạn có chắc chắn muốn nộp bài? Sau khi nộp sẽ không thể thay đổi đáp án.',
      onConfirm: () => {
        handleFinalSubmit();
        setModalConfig(prev => ({ ...prev, isOpen: false }));
      },
    });
  };

  const handleLeave = () => {
    if (isSubmitted) {
      router.push('/exam');
      return;
    }

    // @ts-ignore
    const settings = exam?.exam_settings || {};
    const allowResume = settings.allow_resume !== false;
    const maxAttempts = settings.max_attempts || -1;

    if (!allowResume) {
      setModalConfig({
        isOpen: true,
        title: 'Cảnh báo thoát',
        message: 'Bài thi này KHÔNG cho phép làm lại. Nếu bạn thoát, toàn bộ kết quả sẽ bị hủy. Bạn có chắc chắn muốn thoát?',
        confirmText: 'Thoát và hủy bài',
        isDestructive: true,
        onConfirm: () => {
          clearExamState(examId);
          router.push('/exam');
        }
      });
      return;
    }

    if (maxAttempts === 1) {
      setModalConfig({
        isOpen: true,
        title: 'Cảnh báo thoát',
        message: 'Bạn chỉ có 1 lượt làm bài duy nhất. Việc thoát có thể ảnh hưởng đến lượt thi của bạn. Bạn vẫn muốn thoát?',
        confirmText: 'Vẫn thoát',
        isDestructive: true,
        onConfirm: () => {
          router.push('/exam');
        }
      });
      return;
    }

    router.push('/exam');
  };

  const handlePlayMainAudio = () => {
    if (activeSegmentId && segmentAudioRef.current) {
      segmentAudioRef.current.pause();
      setActiveSegmentId(null);
    }
    if (audioRef.current) {
      const savedSpeed = localStorage.getItem('exam_audio_speed');
      const savedVolume = localStorage.getItem('exam_audio_volume');
      audioRef.current.playbackRate = savedSpeed ? parseFloat(savedSpeed) : 1.0;
      audioRef.current.volume = savedVolume ? parseFloat(savedVolume) : 1.0;
      audioRef.current.play().catch(console.error);
    }
  };

  const handlePauseMainAudio = () => {
    if (audioRef.current) {
      audioRef.current.pause();
    }
  };

  const playSegmentAudio = (questionId: string, startTime: string, endTime: string) => {
    if (isMainAudioPlaying && audioRef.current) {
      audioRef.current.pause();
    }
    
    if (segmentAudioRef.current) {
      segmentAudioRef.current.pause();
      segmentAudioRef.current.currentTime = timeToSeconds(startTime) || 0;
      activeSegmentEndTimeRef.current = timeToSeconds(endTime);
      
      const savedSpeed = localStorage.getItem('exam_audio_speed');
      const savedVolume = localStorage.getItem('exam_audio_volume');
      segmentAudioRef.current.playbackRate = savedSpeed ? parseFloat(savedSpeed) : 1.0;
      segmentAudioRef.current.volume = savedVolume ? parseFloat(savedVolume) : 1.0;
      
      segmentAudioRef.current.play().catch(console.error);
      setActiveSegmentId(questionId);
    }
  };

  const stopSegmentAudio = () => {
    if (segmentAudioRef.current) {
      segmentAudioRef.current.pause();
      setActiveSegmentId(null);
    }
  };

  const formatTime = (seconds: number) => {
    const m = Math.floor(seconds / 60).toString().padStart(2, '0');
    const s = (seconds % 60).toString().padStart(2, '0');
    return `${m}:${s}`;
  };

  if (loading) return <div className="p-8 text-center">Đang tải bài thi...</div>;
  if (error || !exam) return <div className="p-8 text-center text-red-500">{error}</div>;

  const mainAudioUrl = exam.sections?.find(s => s.section_audio_url)?.section_audio_url;
  const allQuestions = exam.sections?.flatMap(s => s.questions) || [];

  return (
    <div className="flex-1 overflow-y-auto w-full p-4 md:p-8 pb-32">
      <div className="max-w-7xl mx-auto flex flex-col xl:flex-row gap-8">
        
        {/* Left Column: Exam Content */}
        <div className="flex-1 bg-surface rounded-[2rem] p-6 shadow-sm border border-outline">
        <button onClick={handleLeave} className="text-secondary hover:text-primary mb-6 flex items-center gap-2">
          &larr; Quay lại danh sách
        </button>

        <div className="flex justify-between items-start mb-2 relative">
          <h1 className="text-3xl font-bold text-primary">{exam.exam_name}</h1>
          
          {/* Settings Dropdown Button */}
          <div className="relative" ref={dropdownRef}>
            <button 
              onClick={() => setShowSettings(!showSettings)}
              className="flex items-center gap-2 px-4 py-2 bg-surface border border-outline hover:bg-hover-bg rounded-xl font-bold text-primary transition-all shadow-sm"
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
        <div className="flex flex-wrap gap-4 text-secondary mb-8 pb-6 border-b">
          <span className="font-bold text-primary bg-primary/10 px-3 py-1 rounded-lg">
            Thời gian: {timeRemaining !== null ? formatTime(timeRemaining) : `${exam.total_time_minutes}:00`}
          </span>
          <span>•</span>
          <span>{exam.total_questions} câu</span>
          <span>•</span>
          <span>Điểm đạt: {exam.passing_score}/{exam.total_score}</span>
        </div>

        {mainAudioUrl && (
          <div className="mb-8 p-6 bg-primary/5 rounded-2xl border border-primary/20 shadow-sm sticky top-4 z-10 backdrop-blur-sm">
            <h2 className="text-lg font-bold text-primary mb-3 flex items-center gap-2">
              🎧 Audio Toàn Bài Thi
            </h2>
            
            {/* Hidden native audio for main */}
            <audio 
              ref={audioRef} 
              src={getMediaUrl(mainAudioUrl)} 
              onTimeUpdate={(e) => setMainAudioCurrentTime(e.currentTarget.currentTime)}
              onEnded={() => setIsMainAudioPlaying(false)}
              onPause={() => setIsMainAudioPlaying(false)}
              onPlay={() => setIsMainAudioPlaying(true)}
              className="hidden" 
            />

            {/* Hidden native audio for segments */}
            <audio 
              ref={segmentAudioRef} 
              src={getMediaUrl(mainAudioUrl)} 
              onTimeUpdate={(e) => {
                if (activeSegmentEndTimeRef.current && e.currentTarget.currentTime >= activeSegmentEndTimeRef.current) {
                  e.currentTarget.pause();
                  setActiveSegmentId(null);
                }
              }}
              onEnded={() => setActiveSegmentId(null)}
              className="hidden" 
            />

            {/* Custom UI for Main Audio */}
            <div className="flex items-center gap-4 bg-white p-3 rounded-xl border border-outline">
              <button 
                onClick={isMainAudioPlaying ? handlePauseMainAudio : handlePlayMainAudio}
                className="w-12 h-12 flex-shrink-0 flex items-center justify-center bg-primary text-white rounded-full hover:bg-primary-hover transition-colors"
              >
                {isMainAudioPlaying ? (
                  <svg className="w-6 h-6" fill="currentColor" viewBox="0 0 24 24"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
                ) : (
                  <svg className="w-6 h-6 ml-1" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                )}
              </button>
              <div className="flex-1">
                 <div className="h-2 bg-gray-200 rounded-full w-full overflow-hidden">
                    <div 
                       className="h-full bg-primary transition-all duration-200" 
                       style={{ width: `${(mainAudioCurrentTime / (audioRef.current?.duration || 1)) * 100}%` }}
                    ></div>
                 </div>
              </div>
              <div className="text-sm font-bold text-secondary font-mono w-24 text-right">
                {formatTime(Math.floor(mainAudioCurrentTime))} / {formatTime(Math.floor(audioRef.current?.duration || 0))}
              </div>
            </div>
          </div>
        )}


        <div className="space-y-12">
          {exam.sections?.map(section => (
            <div key={section.id} className="section-container">
              <h2 className="text-xl font-bold text-primary mb-2">{section.section_name} - Part {section.part_number}</h2>
              {section.instruction && <p className="text-secondary mb-6 italic">{section.instruction}</p>}

              <div className="space-y-8">
                {section.questions.map((question, index) => {
                  const isCorrect = answers[question.question_id] === question.correct_answer;
                  const isAnswered = !!answers[question.question_id];

                  return (
                    <div id={`question-${question.question_id}`} key={question.id} className={`p-6 rounded-2xl border scroll-m-24 ${isSubmitted ? (isCorrect ? 'border-green-300 bg-green-50/30' : 'border-red-300 bg-red-50/30') : 'border-outline-variant bg-surface'}`}>
                      <div className="flex gap-4">
                        <div className="w-8 h-8 flex-shrink-0 bg-primary/10 text-primary font-bold rounded-full flex items-center justify-center">
                          {allQuestions.findIndex(q => q.question_id === question.question_id) + 1}
                        </div>
                        <div className="flex-1 space-y-4">
                          <div className="flex flex-col md:flex-row md:items-center gap-3">
                            {question.question_text && <p className="font-bold text-lg">{question.question_text}</p>}
                            
                            {question.audio_start_time && question.audio_end_time && (
                              <button
                                onClick={() => playSegmentAudio(question.question_id, question.audio_start_time, question.audio_end_time)}
                                className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-semibold border transition-colors ${
                                  activeSegmentId === question.question_id 
                                    ? 'bg-primary text-white border-primary'
                                    : 'bg-primary/10 text-primary border-primary/20 hover:bg-primary/20'
                                }`}
                              >
                                {activeSegmentId === question.question_id ? (
                                  <>
                                    <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
                                    Đang nghe...
                                  </>
                                ) : (
                                  <>
                                    <svg className="w-4 h-4 ml-0.5" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                                    Nghe câu này
                                  </>
                                )}
                              </button>
                            )}
                          </div>
                          
                          <div className={question.question_type === 'true_false' ? "flex flex-col md:flex-row md:items-center gap-6 mt-4" : "mt-4"}>
                            <div className="flex-1">
                              {question.image_url && (
                                <div className="flex justify-center md:justify-start">
                                  <img src={getMediaUrl(question.image_url)} alt="Question Image" className="w-48 h-48 object-cover rounded-2xl shadow-sm border border-outline-variant" />
                                </div>
                              )}
                              {!question.image_url && question.image_description && (
                                <div className="p-4 bg-gray-100 rounded-xl italic text-gray-600 max-w-xs text-center md:text-left">
                                  [Hình ảnh: {question.image_description}]
                                </div>
                              )}
                              
                              {isSubmitted && (question.audio_url || (mainAudioUrl && question.audio_start_time)) && (
                                <div className="mt-4 p-4 bg-gray-50 rounded-xl border border-gray-200">
                                  <p className="text-sm font-bold text-gray-600 mb-2">Nghe lại câu này:</p>
                                  {(() => {
                                    let targetAudioUrl = question.audio_url ? getMediaUrl(question.audio_url) : getMediaUrl(mainAudioUrl!);
                                    if (!question.audio_url && mainAudioUrl && question.audio_start_time) {
                                      const start = timeToSeconds(question.audio_start_time);
                                      const end = timeToSeconds(question.audio_end_time);
                                      if (start !== null) {
                                        targetAudioUrl += `#t=${start}${end !== null ? ',' + end : ''}`;
                                      }
                                    }
                                    return (
                                      <audio controls className="h-10 w-full outline-none">
                                        <source src={targetAudioUrl} type="audio/mpeg" />
                                      </audio>
                                    );
                                  })()}
                                </div>
                              )}
                            </div>

                            {question.question_type === 'true_false' ? (
                              <div className="flex flex-col gap-3 shrink-0 w-32 justify-center">
                                {question.options.map(opt => {
                                  const selected = answers[question.question_id] === opt.option_id;
                                  const isTrue = opt.option_id === 'opt_True';
                                  
                                  let btnClass = "flex items-center justify-center p-3 rounded-xl border-2 transition-all cursor-pointer ";
                                  if (isSubmitted) {
                                    if (opt.option_id === question.correct_answer) {
                                      btnClass += "bg-green-100 border-green-500 text-green-700 shadow-sm";
                                    } else if (selected && opt.option_id !== question.correct_answer) {
                                      btnClass += "bg-red-100 border-red-500 text-red-700 shadow-sm";
                                    } else {
                                      btnClass += "border-outline-variant bg-gray-50 text-gray-300 opacity-60";
                                    }
                                    btnClass = btnClass.replace("cursor-pointer", "cursor-default");
                                  } else {
                                    btnClass += selected ? "border-primary bg-primary/10 text-primary scale-105 shadow-md" : "border-outline-variant bg-gray-100 hover:bg-gray-200 text-secondary";
                                  }

                                  return (
                                    <div key={opt.option_id || opt.id} className={btnClass} onClick={() => handleOptionSelect(question.question_id, opt.option_id)}>
                                      {isTrue ? (
                                        <svg className="w-8 h-8 font-bold" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={4} d="M5 13l4 4L19 7" /></svg>
                                      ) : (
                                        <svg className="w-8 h-8 font-bold" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={4} d="M6 18L18 6M6 6l12 12" /></svg>
                                      )}
                                    </div>
                                  );
                                })}
                              </div>
                            ) : (
                              <div className={`mt-6 ${question.options.every(opt => !opt.text) ? 'grid grid-cols-1 md:grid-cols-3 gap-6' : 'space-y-3'}`}>
                                {question.options.map((opt, optIndex) => {
                                  const selected = answers[question.question_id] === opt.option_id;
                                  const isImageOnly = !opt.text;
                                  
                                  let optionClass = `relative flex ${isImageOnly ? 'flex-col justify-center items-center p-2' : 'items-center gap-4 p-4'} rounded-2xl border-2 cursor-pointer transition-all `;
                                  
                                  if (isSubmitted) {
                                    if (opt.option_id === question.correct_answer) {
                                      optionClass += "bg-green-50 border-green-500 text-green-900 shadow-sm";
                                    } else if (selected && opt.option_id !== question.correct_answer) {
                                      optionClass += "bg-red-50 border-red-400 text-red-900";
                                    } else {
                                      optionClass += "border-outline-variant opacity-60 bg-surface";
                                    }
                                    optionClass = optionClass.replace("cursor-pointer", "cursor-default");
                                  } else {
                                    optionClass += selected ? "border-primary bg-primary/5 shadow-md scale-[1.02]" : "border-outline-variant hover:border-primary/40 hover:bg-hover-bg bg-surface";
                                  }

                                  const letter = String.fromCharCode(65 + optIndex); // A, B, C...

                                  return (
                                    <div key={opt.option_id || opt.id} className={optionClass} onClick={() => handleOptionSelect(question.question_id, opt.option_id)}>
                                      {isImageOnly ? (
                                        <>
                                          <div className="absolute top-0 left-0 bg-secondary/80 text-white w-8 h-8 flex items-center justify-center rounded-br-xl rounded-tl-xl font-bold z-10">
                                            {letter}
                                          </div>
                                          <div className="w-full aspect-[4/3] rounded-xl overflow-hidden bg-gray-50 flex items-center justify-center relative">
                                            {opt.image_url ? (
                                              <img src={getMediaUrl(opt.image_url)} alt="Option" className="w-full h-full object-cover" />
                                            ) : opt.image_description ? (
                                              <span className="italic text-gray-500 text-xs p-4 text-center">[{opt.image_description}]</span>
                                            ) : null}
                                          </div>
                                          {isSubmitted && opt.option_id === question.correct_answer && (
                                            <div className="absolute inset-[-4px] border-[4px] border-green-500 rounded-2xl pointer-events-none z-20"></div>
                                          )}
                                        </>
                                      ) : (
                                        <>
                                          <div className={`w-6 h-6 shrink-0 rounded-full border-2 flex items-center justify-center ${selected ? 'border-primary bg-primary/20' : 'border-gray-300'}`}>
                                            {selected && <div className="w-3 h-3 bg-primary rounded-full"></div>}
                                          </div>
                                          <div className="flex-1 text-lg">
                                            {opt.text}
                                            {opt.image_url && (
                                              <div className="mt-3 flex justify-center md:justify-start">
                                                <img src={getMediaUrl(opt.image_url)} alt="Option" className="max-w-[200px] max-h-[150px] object-cover rounded-xl border border-gray-200 shadow-sm" />
                                              </div>
                                            )}
                                          </div>
                                        </>
                                      )}
                                    </div>
                                  );
                                })}
                              </div>
                            )}
                          </div>

                          {isSubmitted && exam.show_explanation_after === 'exam_submitted' && (
                            <div className="mt-6 p-4 bg-blue-50 text-blue-900 rounded-xl border border-blue-200 text-sm">
                              <p className="font-bold mb-1">Giải thích:</p>
                              {question.audio_script && <p className="mb-2"><strong>Audio script:</strong> {question.audio_script}</p>}
                              <p>{question.explanation || 'Không có giải thích chi tiết.'}</p>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </div>

        {/* Right Column: Navigation Sidebar */}
        <div className="w-full xl:w-96 flex-shrink-0">
          <div className="sticky top-4 max-h-[calc(100vh-2rem)] flex flex-col gap-6">
            <div className="bg-surface rounded-[2rem] p-6 shadow-sm border border-outline flex flex-col min-h-0">
              <h2 className="text-xl font-bold text-primary mb-4 flex-shrink-0 flex items-center justify-between">
                <span>Danh sách câu hỏi</span>
                <span className="text-sm font-normal text-secondary bg-gray-100 px-3 py-1 rounded-full">
                  {Object.keys(answers).length} / {exam.total_questions}
                </span>
              </h2>
              
              <div className="flex-1 overflow-y-auto pr-2 pb-2 [&::-webkit-scrollbar]:w-2 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:bg-gray-300 [&::-webkit-scrollbar-thumb]:rounded-full">
                <div className="flex flex-wrap gap-2">
                  {allQuestions.map((q, idx) => {
                    const isAnswered = !!answers[q.question_id];
                    const isCorrect = answers[q.question_id] === q.correct_answer;
                    
                    let btnClass = "w-10 h-10 rounded-xl font-bold text-sm flex items-center justify-center border-2 transition-all duration-200 ";
                    
                    if (isSubmitted) {
                      if (isCorrect) btnClass += " bg-green-100 text-green-700 border-green-400";
                      else btnClass += " bg-red-100 text-red-700 border-red-400";
                    } else {
                      if (isAnswered) btnClass += " bg-primary text-white border-primary shadow-sm transform hover:scale-105";
                      else btnClass += " bg-white text-secondary border-outline-variant hover:border-primary";
                    }

                    return (
                      <button
                        key={`nav-q-${q.question_id}`}
                        onClick={() => {
                          document.getElementById(`question-${q.question_id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
                        }}
                        className={btnClass}
                        title={isSubmitted ? (isCorrect ? 'Đúng' : 'Sai') : (isAnswered ? 'Đã làm' : 'Chưa làm')}
                      >
                        {idx + 1}
                      </button>
                    );
                  })}
                </div>

                {!isSubmitted ? (
                  <div className="mt-8 pt-6 border-t border-outline">
                    <button 
                      onClick={handleSubmit}
                      className="w-full bg-primary hover:bg-primary-hover text-white font-bold py-4 rounded-xl shadow-md transition-transform active:scale-95"
                    >
                      Nộp Bài
                    </button>
                  </div>
                ) : (
                  <div className="mt-8 pt-6 border-t border-outline">
                    <div className={`p-4 rounded-xl shadow-inner border ${score >= exam.passing_score ? 'bg-green-50 border-green-200 text-green-800' : 'bg-red-50 border-red-200 text-red-800'}`}>
                      <h2 className="text-xl font-bold mb-2">Kết quả bài thi</h2>
                      <div className="flex items-baseline gap-2 mb-1">
                        <span className="text-3xl font-black">{score}</span>
                        <span className="text-base opacity-70">/ {exam.total_score} điểm</span>
                      </div>
                      <p className="text-sm font-medium leading-snug">{score >= exam.passing_score ? '🎉 Chúc mừng! Bạn đã đạt yêu cầu.' : 'Rất tiếc! Bạn chưa đạt điểm yêu cầu.'}</p>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
      
      <ConfirmModal
        isOpen={modalConfig.isOpen}
        title={modalConfig.title}
        message={modalConfig.message}
        confirmText={modalConfig.confirmText}
        isDestructive={modalConfig.isDestructive}
        onConfirm={modalConfig.onConfirm}
        onCancel={() => setModalConfig(prev => ({ ...prev, isOpen: false }))}
      />
    </div>
  );
}
