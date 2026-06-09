import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { environment } from '@env/environment';
import { Book } from '../models/book';

@Injectable({ providedIn: 'root' })
export class BookService {
  private readonly http = inject(HttpClient);

  private readonly _books = signal<Book[]>([]);
  private readonly _selectedIds = signal<Set<string>>(new Set());
  private readonly _loaded = signal(false);

  readonly books = this._books.asReadonly();
  readonly loaded = this._loaded.asReadonly();
  readonly selectedBookIds = computed(() => Array.from(this._selectedIds()));
  readonly hasSelection = computed(() => this._selectedIds().size > 0);

  async loadBooks(): Promise<void> {
    const books = await firstValueFrom(
      this.http.get<Book[]>(`${environment.apiBaseUrl}/books`),
    );
    this._books.set(books);
    this._loaded.set(true);
  }

  toggleBook(bookId: string): void {
    const current = new Set(this._selectedIds());
    if (current.has(bookId)) {
      current.delete(bookId);
    } else {
      current.add(bookId);
    }
    this._selectedIds.set(current);
  }

  isSelected(bookId: string): boolean {
    return this._selectedIds().has(bookId);
  }

  clearSelection(): void {
    this._selectedIds.set(new Set());
  }
}
