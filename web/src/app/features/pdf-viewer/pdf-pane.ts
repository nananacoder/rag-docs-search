import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  Renderer2,
  ViewEncapsulation,
  computed,
  effect,
  inject,
} from '@angular/core';
import { NgxExtendedPdfViewerModule, PageRenderedEvent } from 'ngx-extended-pdf-viewer';
import { MatIconModule } from '@angular/material/icon';
import { environment } from '@env/environment';
import { QueryService } from '@core/services/query.service';

/**
 * Phase 2 source pane: renders the actual PDF page for the active citation
 * and draws its (page, bbox) as a highlight box — the concrete win over
 * Phase 1, whose Standard-tier retrieval returned no page or bbox at all.
 *
 * bbox is stored normalized (0-1, top-left origin — matches pymupdf and
 * CSS), so the overlay positions with plain percentages: zoom-independent,
 * no pixel math.
 *
 * ViewEncapsulation.None: the highlight div is injected into pdf.js's own
 * DOM (outside this component's view), so its class must not be scoped.
 */
@Component({
  selector: 'app-pdf-pane',
  standalone: true,
  imports: [NgxExtendedPdfViewerModule, MatIconModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  encapsulation: ViewEncapsulation.None,
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
          @if (!c.bbox) { · <span class="no-bbox">no region</span> }
        </div>
      </div>

      <div class="viewer">
        <ngx-extended-pdf-viewer
          [src]="pdfSrc"
          [page]="activePage()"
          [showToolbar]="false"
          [showSidebarButton]="false"
          [textLayer]="false"
          [showBorders]="false"
          zoom="page-width"
          (pageRendered)="onPageRendered($event)"
        />
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
    app-pdf-pane {
      display: flex;
      flex-direction: column;
      height: 100%;
      padding: 16px;
      background: var(--mat-sys-surface-container-low);
      border-left: 1px solid var(--mat-sys-outline-variant);
      overflow: hidden;
    }
    app-pdf-pane .header { display: flex; align-items: center; gap: 8px; }
    app-pdf-pane .header h2 { margin: 0; font-size: 18px; }
    app-pdf-pane .meta { margin: 12px 0; }
    app-pdf-pane .title { font-weight: 500; }
    app-pdf-pane .sub { font-size: 13px; color: var(--mat-sys-on-surface-variant); }
    app-pdf-pane .no-bbox { font-style: italic; opacity: 0.7; }
    app-pdf-pane .viewer {
      flex: 1;
      min-height: 280px;
      border-radius: 8px;
      overflow: hidden;
      margin-bottom: 16px;
      background: var(--mat-sys-surface-container);
    }
    app-pdf-pane .snippet .label {
      font-size: 12px; text-transform: uppercase;
      color: var(--mat-sys-on-surface-variant);
    }
    app-pdf-pane blockquote {
      margin: 4px 0 0;
      padding: 8px 12px;
      border-left: 3px solid var(--mat-sys-primary);
      background: var(--mat-sys-surface-container);
      font-size: 13px;
      line-height: 1.5;
    }
    app-pdf-pane .big-icon { font-size: 48px; width: 48px; height: 48px; opacity: 0.4; }
    app-pdf-pane .empty {
      flex: 1;
      display: flex; flex-direction: column;
      align-items: center; justify-content: center;
      color: var(--mat-sys-on-surface-variant);
      text-align: center;
    }
    /* Injected into pdf.js page divs — must be unscoped. */
    .bbox-highlight {
      position: absolute;
      border: 2px solid var(--mat-sys-primary, #6750a4);
      background: color-mix(in srgb, var(--mat-sys-primary, #6750a4) 22%, transparent);
      border-radius: 2px;
      pointer-events: none;
      box-shadow: 0 0 0 9999px color-mix(in srgb, black 8%, transparent);
      animation: bbox-pulse 1.2s ease-out;
    }
    @keyframes bbox-pulse {
      0% { box-shadow: 0 0 0 4px var(--mat-sys-primary, #6750a4); }
      100% { box-shadow: 0 0 0 9999px color-mix(in srgb, black 8%, transparent); }
    }
  `],
})
export class PdfPane {
  readonly query = inject(QueryService);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly renderer = inject(Renderer2);

  readonly pdfSrc = environment.pdfSrc;
  readonly activePage = computed(() => this.query.activeCitation()?.page ?? 1);

  constructor() {
    // When the citation changes to a page pdf.js has already rendered,
    // pageRendered won't fire again — draw directly on the cached div.
    effect(() => {
      this.query.activeCitation();
      queueMicrotask(() => this.redrawActive());
    });
  }

  onPageRendered(event: PageRenderedEvent): void {
    const c = this.query.activeCitation();
    if (c && event.pageNumber === c.page) {
      this.drawHighlight(event.source.div as HTMLElement, c.bbox);
    }
  }

  private redrawActive(): void {
    const c = this.query.activeCitation();
    if (!c) return;
    const pageDiv = this.host.nativeElement.querySelector<HTMLElement>(
      `.page[data-page-number="${c.page}"]`,
    );
    if (pageDiv) this.drawHighlight(pageDiv, c.bbox);
  }

  private drawHighlight(
    pageDiv: HTMLElement,
    bbox: { x0: number; y0: number; x1: number; y1: number } | null,
  ): void {
    this.host.nativeElement
      .querySelectorAll('.bbox-highlight')
      .forEach((n: Element) => n.remove());
    if (!bbox) return;
    const hl = this.renderer.createElement('div');
    this.renderer.addClass(hl, 'bbox-highlight');
    this.renderer.setStyle(hl, 'left', `${bbox.x0 * 100}%`);
    this.renderer.setStyle(hl, 'top', `${bbox.y0 * 100}%`);
    this.renderer.setStyle(hl, 'width', `${(bbox.x1 - bbox.x0) * 100}%`);
    this.renderer.setStyle(hl, 'height', `${(bbox.y1 - bbox.y0) * 100}%`);
    this.renderer.appendChild(pageDiv, hl);
  }
}
