import { ChangeDetectionStrategy, Component, OnInit, inject } from '@angular/core';
import { MatListModule } from '@angular/material/list';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatIconModule } from '@angular/material/icon';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { BookService } from '@core/services/book.service';

@Component({
  selector: 'app-library-pane',
  standalone: true,
  imports: [
    MatListModule,
    MatCheckboxModule,
    MatIconModule,
    MatButtonModule,
    MatProgressSpinnerModule,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="header">
      <mat-icon>library_books</mat-icon>
      <h2>Library</h2>
      @if (books.hasSelection()) {
        <button mat-icon-button (click)="books.clearSelection()" aria-label="Clear selection">
          <mat-icon>clear_all</mat-icon>
        </button>
      }
    </div>
    <p class="hint">
      @if (books.hasSelection()) {
        Searching within {{ books.selectedBookIds().length }} selected book(s)
      } @else {
        All books included by default
      }
    </p>

    @if (!books.loaded()) {
      <div class="loading"><mat-spinner diameter="32" /></div>
    } @else if (books.books().length === 0) {
      <p class="empty">No books indexed yet. Upload a PDF to GCS to get started.</p>
    } @else {
      <mat-selection-list [multiple]="true" class="book-list">
        @for (book of books.books(); track book.bookId) {
          <mat-list-option
            [value]="book.bookId"
            [selected]="books.isSelected(book.bookId)"
            (selectedChange)="books.toggleBook(book.bookId)"
          >
            <div matListItemTitle>{{ book.title }}</div>
            <div matListItemLine class="meta">
              {{ book.author }}{{ book.year ? ' · ' + book.year : '' }}
            </div>
            <div matListItemLine class="meta">{{ book.pageCount }} pages</div>
          </mat-list-option>
        }
      </mat-selection-list>
    }
  `,
  styles: [`
    :host {
      display: flex;
      flex-direction: column;
      height: 100%;
      padding: 16px;
      background: var(--mat-sys-surface-container-low);
      border-right: 1px solid var(--mat-sys-outline-variant);
      overflow: hidden;
    }
    .header {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .header h2 { margin: 0; font-size: 18px; flex: 1; }
    .hint { color: var(--mat-sys-on-surface-variant); font-size: 13px; margin: 4px 0 16px; }
    .loading, .empty { padding: 24px; text-align: center; color: var(--mat-sys-on-surface-variant); }
    .book-list { flex: 1; overflow-y: auto; }
    .meta { color: var(--mat-sys-on-surface-variant); font-size: 12px; }
  `],
})
export class LibraryPane implements OnInit {
  readonly books = inject(BookService);

  async ngOnInit(): Promise<void> {
    try {
      await this.books.loadBooks();
    } catch (err) {
      console.error('Failed to load books', err);
    }
  }
}
