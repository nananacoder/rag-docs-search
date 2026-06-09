import { ChangeDetectionStrategy, Component } from '@angular/core';
import { LibraryPane } from '../library/library-pane';
import { ConversationPane } from '../conversation/conversation-pane';
import { PdfPane } from '../pdf-viewer/pdf-pane';

@Component({
  selector: 'app-workspace',
  standalone: true,
  imports: [LibraryPane, ConversationPane, PdfPane],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="shell">
      <aside class="left"><app-library-pane /></aside>
      <main class="center"><app-conversation-pane /></main>
      <aside class="right"><app-pdf-pane /></aside>
    </div>
  `,
  styles: [`
    :host { display: block; height: 100vh; }
    .shell {
      display: grid;
      grid-template-columns: 300px 1fr 400px;
      height: 100%;
    }
    .left, .center, .right { height: 100%; overflow: hidden; }
    @media (max-width: 1100px) {
      .shell { grid-template-columns: 260px 1fr 340px; }
    }
  `],
})
export class Workspace {}
