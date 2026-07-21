export const environment = {
  production: false,
  apiBaseUrl: '/api',
  // Local dev: drop the (gitignored) PDF into web/src/assets/.
  // Prod: point at an API/GCS-served URL.
  pdfSrc: '/assets/astronomy-2e.pdf',
};
