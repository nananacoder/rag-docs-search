import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatCardModule } from '@angular/material/card';
import { MatChipsModule } from '@angular/material/chips';
import { BookService } from '@core/services/book.service';
import { QueryService } from '@core/services/query.service';
import { AnswerView } from './answer-view';

@Component({
  selector: 'app-conversation-pane',
  standalone: true,
  imports: [
    FormsModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatIconModule,
    MatCardModule,
    MatChipsModule,
    AnswerView,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="header">
      <mat-icon>chat</mat-icon>
      <h2>Ask the library</h2>
      @if (query.turns().length > 0) {
        <button mat-icon-button (click)="query.clearHistory()" aria-label="Clear history">
          <mat-icon>restart_alt</mat-icon>
        </button>
      }
    </div>

    <div class="turns">
      @for (turn of query.turns(); track turn.id) {
        <app-answer-view [turn]="turn" />
      } @empty {
        <div class="empty">
          <mat-icon>menu_book</mat-icon>
          <p>Ask a question about the books in your library.</p>
          <p class="examples">
            Try: <em>"What does Gibbon identify as the immediate cause of Commodus's assassination?"</em>
          </p>
        </div>
      }
    </div>

    <form class="composer" (submit)="submit($event)">
      <mat-form-field appearance="outline" class="input-field">
        <mat-label>Your question</mat-label>
        <textarea
          matInput
          rows="2"
          [(ngModel)]="draft"
          name="q"
          [disabled]="query.streaming()"
          (keydown.enter)="handleEnter($event)"
        ></textarea>
      </mat-form-field>
      <div class="actions">
        @if (books.hasSelection()) {
          <mat-chip-set>
            <mat-chip>{{ books.selectedBookIds().length }} book(s) scoped</mat-chip>
          </mat-chip-set>
        }
        @if (query.streaming()) {
          <button mat-stroked-button type="button" color="warn" (click)="query.cancel()">
            <mat-icon>stop</mat-icon> Stop
          </button>
        } @else {
          <button mat-flat-button type="submit" color="primary" [disabled]="!canSubmit()">
            <mat-icon>send</mat-icon> Ask
          </button>
        }
      </div>
    </form>
  `,
  styles: [`
    :host {
      display: flex;
      flex-direction: column;
      height: 100%;
      background: var(--mat-sys-surface);
      overflow: hidden;
    }
    .header {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 16px;
      border-bottom: 1px solid var(--mat-sys-outline-variant);
    }
    .header h2 { margin: 0; font-size: 18px; flex: 1; }
    .turns {
      flex: 1;
      overflow-y: auto;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 16px;
    }
    .empty {
      margin: auto;
      text-align: center;
      color: var(--mat-sys-on-surface-variant);
      max-width: 460px;
    }
    .empty mat-icon { font-size: 48px; width: 48px; height: 48px; opacity: 0.5; }
    .examples { font-size: 14px; }
    .composer {
      display: flex;
      flex-direction: column;
      padding: 12px 16px 16px;
      gap: 8px;
      border-top: 1px solid var(--mat-sys-outline-variant);
      background: var(--mat-sys-surface-container-lowest);
    }
    .input-field { width: 100%; }
    .actions { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
  `],
})
export class ConversationPane {
  readonly books = inject(BookService);
  readonly query = inject(QueryService);

  readonly draft = signal('');

  canSubmit(): boolean {
    return this.draft().trim().length > 0 && !this.query.streaming();
  }

  submit(event: Event): void {
    event.preventDefault();
    if (!this.canSubmit()) return;
    const question = this.draft().trim();
    this.draft.set('');
    void this.query.ask({
      question,
      bookIds: this.books.hasSelection() ? this.books.selectedBookIds() : undefined,
    });
  }

  handleEnter(event: Event): void {
    const ke = event as KeyboardEvent;
    if (ke.shiftKey) return;
    this.submit(event);
  }
}
