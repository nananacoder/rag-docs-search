export interface BoundingBox {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

export interface Citation {
  index: number;
  bookId: string;
  bookTitle: string;
  author: string;
  chapterNum: number | null;
  chapterTitle: string | null;
  page: number;
  snippet: string;
  bbox: BoundingBox | null;
}
