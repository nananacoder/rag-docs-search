import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { MatIconModule } from '@angular/material/icon';
import { QueryService } from '@core/services/query.service';

@Component({
  selector: 'app-pdf-pane',
  standalone: true,
  imports: [MatIconModule, DecimalPipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @let c = query.activeCitation();
    <div class="header">
      <mat-icon>picture_as_pdf</mat-icon>
      <h2>Source</h2>
    </div>

    @if (c) {
      <div class="meta">
        <div class="title">{{ c.author }}, {{ c.bookTitle }}</div>
        <div class="sub">
          @if (c.chapterNum) { Ch. {{ c.chapterNum }}{{ c.chapterTitle ? ': ' + c.chapterTitle : '' }} · }
          p. {{ c.page }}
        </div>
      </div>

      <div class="viewer-placeholder">
        <!--
          Phase 1: simple placeholder.
          Phase 2: replace with <ngx-extended-pdf-viewer [src]="pdfSrc()" [page]="c.page" />
                   + bbox overlay using c.bbox.
        -->
        <mat-icon class="big-icon">description</mat-icon>
        <p>PDF preview placeholder</p>
        <p class="hint">Page {{ c.page }} of {{ c.bookTitle }}</p>
        @if (c.bbox) {
          <p class="hint">
            bbox: ({{ c.bbox.x0 | number:'1.0-0' }}, {{ c.bbox.y0 | number:'1.0-0' }})
            → ({{ c.bbox.x1 | number:'1.0-0' }}, {{ c.bbox.y1 | number:'1.0-0' }})
          </p>
        }
      </div>

      <div class="snippet">
        <div class="label">Excerpt</div>
        <blockquote>{{ c.snippet }}</blockquote>
      </div>
    } @else {
      <div class="empty">
        <mat-icon class="big-icon">description</mat-icon>
        <p>Click a citation to view its source page.</p>
      </div>
    }
  `,
  styles: [`
    :host {
      display: flex;
      flex-direction: column;
      height: 100%;
      padding: 16px;
      background: var(--mat-sys-surface-container-low);
      border-left: 1px solid var(--mat-sys-outline-variant);
      overflow: hidden;
    }
    .header { display: flex; align-items: center; gap: 8px; }
    .header h2 { margin: 0; font-size: 18px; }
    .meta { margin: 12px 0; }
    .title { font-weight: 500; }
    .sub { font-size: 13px; color: var(--mat-sys-on-surface-variant); }
    .viewer-placeholder {
      flex: 1;
      min-height: 280px;
      border: 2px dashed var(--mat-sys-outline-variant);
      border-radius: 8px;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      color: var(--mat-sys-on-surface-variant);
      margin-bottom: 16px;
      padding: 16px;
      text-align: center;
    }
    .big-icon { font-size: 48px; width: 48px; height: 48px; opacity: 0.4; }
    .hint { font-size: 12px; margin: 4px 0; }
    .snippet .label { font-size: 12px; text-transform: uppercase; color: var(--mat-sys-on-surface-variant); }
    blockquote {
      margin: 4px 0 0;
      padding: 8px 12px;
      border-left: 3px solid var(--mat-sys-primary);
      background: var(--mat-sys-surface-container);
      font-size: 13px;
      line-height: 1.5;
    }
    .empty {
      flex: 1;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      color: var(--mat-sys-on-surface-variant);
      text-align: center;
    }
  `],
})
export class PdfPane {
  readonly query = inject(QueryService);
}
