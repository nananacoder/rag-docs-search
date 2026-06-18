import { Injectable, computed, signal } from '@angular/core';
import { environment } from '@env/environment';
import { Citation } from '../models/citation';
import { QueryEvent, QueryRequest } from '../models/query';

interface Turn {
  id: string;
  question: string;
  answer: string;
  citations: Citation[];
  status: 'streaming' | 'done' | 'error';
  error?: string;
  metrics?: {
    inputTokens: number;
    outputTokens: number;
    totalMs: number;
    model: string;
  };
}

@Injectable({ providedIn: 'root' })
export class QueryService {
  private readonly _turns = signal<Turn[]>([]);
  private readonly _activeCitation = signal<Citation | null>(null);
  private readonly _streaming = signal(false);
  private abortController: AbortController | null = null;

  readonly turns = this._turns.asReadonly();
  readonly activeCitation = this._activeCitation.asReadonly();
  readonly streaming = this._streaming.asReadonly();
  readonly latestTurn = computed(() => this._turns().at(-1));

  async ask(request: QueryRequest): Promise<void> {
    if (this._streaming()) return;

    this.abortController = new AbortController();
    this._streaming.set(true);

    const turnId = crypto.randomUUID();
    const turn: Turn = {
      id: turnId,
      question: request.question,
      answer: '',
      citations: [],
      status: 'streaming',
    };
    this._turns.update((ts) => [...ts, turn]);

    try {
      const response = await fetch(`${environment.apiBaseUrl}/query`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
        body: JSON.stringify(request),
        signal: this.abortController.signal,
      });

      if (!response.ok || !response.body) {
        throw new Error(`HTTP ${response.status}`);
      }

      const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += value;

        const events = buffer.split('\n\n');
        buffer = events.pop() ?? '';

        for (const chunk of events) {
          const event = this.parseSseEvent(chunk);
          if (event) this.handleEvent(turnId, event);
        }
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      this.updateTurn(turnId, (t) => ({ ...t, status: 'error', error: msg }));
    } finally {
      this._streaming.set(false);
      this.abortController = null;
    }
  }

  cancel(): void {
    this.abortController?.abort();
  }

  selectCitation(citation: Citation | null): void {
    this._activeCitation.set(citation);
  }

  clearHistory(): void {
    this._turns.set([]);
    this._activeCitation.set(null);
  }

  private parseSseEvent(chunk: string): QueryEvent | null {
    const dataLine = chunk
      .split('\n')
      .find((l) => l.startsWith('data:'));
    if (!dataLine) return null;
    const payload = dataLine.slice(5).trim();
    if (!payload) return null;
    try {
      return JSON.parse(payload) as QueryEvent;
    } catch {
      return null;
    }
  }

  private handleEvent(turnId: string, event: QueryEvent): void {
    switch (event.type) {
      case 'citations':
        this.updateTurn(turnId, (t) => ({ ...t, citations: event.citations }));
        break;
      case 'token':
        this.updateTurn(turnId, (t) => ({ ...t, answer: t.answer + event.text }));
        break;
      case 'done':
        this.updateTurn(turnId, (t) => ({
          ...t,
          status: 'done',
          metrics: {
            inputTokens: event.inputTokens,
            outputTokens: event.outputTokens,
            totalMs: event.totalMs,
            model: event.model,
          },
        }));
        break;
      case 'error':
        this.updateTurn(turnId, (t) => ({ ...t, status: 'error', error: event.message }));
        break;
    }
  }

  private updateTurn(turnId: string, mutate: (t: Turn) => Turn): void {
    this._turns.update((ts) => ts.map((t) => (t.id === turnId ? mutate(t) : t)));
  }
}
