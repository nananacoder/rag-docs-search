import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatExpansionModule } from '@angular/material/expansion';
import { MatButtonModule } from '@angular/material/button';
import { Citation } from '@core/models/citation';
import { QueryService } from '@core/services/query.service';

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

interface AnswerSegment {
  kind: 'text' | 'cite';
  value: string;
  citationIndex?: number;
}

@Component({
  selector: 'app-answer-view',
  standalone: true,
  imports: [MatCardModule, MatIconModule, MatExpansionModule, MatButtonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @let t = turn();
    <mat-card appearance="outlined" class="turn">
      <div class="question">
        <mat-icon class="q-icon">person</mat-icon>
        <div>{{ t.question }}</div>
      </div>

      <div class="answer">
        <mat-icon class="a-icon">auto_awesome</mat-icon>
        <div class="answer-body">
          @if (t.status === 'error') {
            <span class="error">Error: {{ t.error }}</span>
          } @else {
            @for (seg of segments(); track $index) {
              @if (seg.kind === 'text') {
                <span>{{ seg.value }}</span>
              } @else {
                <button
                  class="citation-pill"
                  type="button"
                  (click)="activateCitation(seg.citationIndex!)"
                >[{{ seg.citationIndex }}]</button>
              }
            }
            @if (t.status === 'streaming') {
              <span class="cursor">▍</span>
            }
          }
        </div>
      </div>

      @if (t.citations.length > 0) {
        <mat-expansion-panel class="sources" hideToggle>
          <mat-expansion-panel-header>
            <mat-panel-title>
              <mat-icon>source</mat-icon>
              <span>{{ t.citations.length }} source(s)</span>
            </mat-panel-title>
          </mat-expansion-panel-header>
          <ul class="source-list">
            @for (c of t.citations; track c.index) {
              <li>
                <button class="source-item" type="button" (click)="query.selectCitation(c)">
                  <span class="idx">[{{ c.index }}]</span>
                  <div>
                    <div class="src-title">{{ c.author }}, {{ c.bookTitle }}</div>
                    <div class="src-meta">
                      @if (c.chapterNum) { Ch. {{ c.chapterNum }} · }
                      p. {{ c.page }}
                    </div>
                    <div class="snippet">{{ c.snippet }}</div>
                  </div>
                </button>
              </li>
            }
          </ul>
        </mat-expansion-panel>
      }

      @if (t.metrics) {
        <div class="metrics">
          {{ t.metrics.model }} · {{ t.metrics.inputTokens }}→{{ t.metrics.outputTokens }} tok ·
          {{ t.metrics.totalMs }}ms
        </div>
      }
    </mat-card>
  `,
  styles: [`
    .turn { padding: 16px; }
    .question, .answer { display: flex; gap: 12px; margin-bottom: 12px; }
    .q-icon { color: var(--mat-sys-primary); }
    .a-icon { color: var(--mat-sys-tertiary); }
    .question { font-weight: 500; }
    .answer-body { white-space: pre-wrap; line-height: 1.5; flex: 1; }
    .citation-pill {
      background: var(--mat-sys-primary-container);
      color: var(--mat-sys-on-primary-container);
      border: none;
      border-radius: 10px;
      padding: 0 6px;
      margin: 0 2px;
      cursor: pointer;
      font-size: 0.85em;
      font-weight: 600;
    }
    .citation-pill:hover { filter: brightness(1.05); }
    .cursor { animation: blink 1s infinite; color: var(--mat-sys-primary); }
    @keyframes blink { 50% { opacity: 0; } }
    .error { color: var(--mat-sys-error); }
    .sources { margin-top: 8px; }
    .sources mat-panel-title { gap: 8px; display: flex; align-items: center; font-size: 13px; }
    .source-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 8px; }
    .source-item {
      display: flex; gap: 12px; width: 100%; text-align: left;
      padding: 8px; background: transparent; border: 1px solid var(--mat-sys-outline-variant);
      border-radius: 6px; cursor: pointer;
    }
    .source-item:hover { background: var(--mat-sys-surface-container); }
    .idx { font-weight: 600; color: var(--mat-sys-primary); }
    .src-title { font-weight: 500; font-size: 14px; }
    .src-meta { font-size: 12px; color: var(--mat-sys-on-surface-variant); margin-bottom: 4px; }
    .snippet { font-size: 13px; color: var(--mat-sys-on-surface-variant); }
    .metrics { font-size: 11px; color: var(--mat-sys-on-surface-variant); margin-top: 8px; }
  `],
})
export class AnswerView {
  readonly turn = input.required<Turn>();
  readonly query = inject(QueryService);

  readonly segments = computed<AnswerSegment[]>(() => {
    const text = this.turn().answer;
    const out: AnswerSegment[] = [];
    const pattern = /\[(\d+)\]/g;
    let last = 0;
    let match: RegExpExecArray | null;
    while ((match = pattern.exec(text)) !== null) {
      if (match.index > last) {
        out.push({ kind: 'text', value: text.slice(last, match.index) });
      }
      out.push({ kind: 'cite', value: match[0], citationIndex: Number(match[1]) });
      last = match.index + match[0].length;
    }
    if (last < text.length) {
      out.push({ kind: 'text', value: text.slice(last) });
    }
    return out;
  });

  activateCitation(idx: number): void {
    const c = this.turn().citations.find((c) => c.index === idx);
    if (c) this.query.selectCitation(c);
  }
}
