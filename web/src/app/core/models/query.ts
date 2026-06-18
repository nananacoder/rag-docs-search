import { Citation } from './citation';

export interface QueryRequest {
  question: string;
  bookIds?: string[];
  topK?: number;
}

export type QueryEventType = 'citations' | 'token' | 'done' | 'error';

export interface CitationsEvent {
  type: 'citations';
  citations: Citation[];
}

export interface TokenEvent {
  type: 'token';
  text: string;
}

export interface DoneEvent {
  type: 'done';
  inputTokens: number;
  outputTokens: number;
  totalMs: number;
  model: string;
}

export interface ErrorEvent {
  type: 'error';
  message: string;
}

export type QueryEvent = CitationsEvent | TokenEvent | DoneEvent | ErrorEvent;
