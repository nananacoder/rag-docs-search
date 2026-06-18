export interface Book {
  bookId: string;
  title: string;
  author: string;
  year: number | null;
  pageCount: number;
  gcsUri: string;
}
