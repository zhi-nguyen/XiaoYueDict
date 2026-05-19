export interface Notebook {
  id: number;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
  word_count_annotated?: number;
}

export interface Word {
  id: number;
  notebook: number;
  vocabulary: string;
  pinyin: string;
  meaning: string;
  notes: string;
  created_at: string;
  updated_at: string;
}
