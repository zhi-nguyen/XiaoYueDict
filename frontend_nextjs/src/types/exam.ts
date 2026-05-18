export interface Option {
  id: number;
  option_id: string;
  text: string;
  image_url: string;
  image_description: string;
  ordering: number;
}

export interface Question {
  id: number;
  question_id: string;
  question_type: 'true_false' | 'multiple_choice' | 'fill_blank' | 'matching' | 'ordering';
  difficulty: 'easy' | 'medium' | 'hard';
  points: number;
  tags: string[];
  audio_url: string;
  audio_start_time: string;
  audio_end_time: string;
  audio_script: string;
  question_text: string;
  image_url: string;
  image_description: string;
  correct_answer: string;
  explanation: string;
  ordering: number;
  options: Option[];
}

export interface Section {
  id: number;
  section_id: string;
  section_name: 'Listening' | 'Reading' | 'Writing';
  part_number: number;
  instruction: string;
  section_audio_url: string;
  ordering: number;
  questions: Question[];
}

export interface Exam {
  id: number;
  exam_id: string;
  exam_name: string;
  exam_version: string;
  level: string;
  total_questions: number;
  total_time_minutes: number;
  total_score: number;
  passing_score: number;
  allow_resume: boolean;
  max_attempts: number;
  shuffle_questions: boolean;
  shuffle_options: boolean;
  show_explanation_after: string;
  status: number;
  created_at: string;
  sections?: Section[];
}
