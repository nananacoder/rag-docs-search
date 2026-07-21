export const environment = {
  production: false,
  apiBaseUrl: '/api',
  // PDF is streamed from GCS via the same-origin API proxy in both dev and
  // prod (needs GCP ADC locally, since the corpus lives in Cloud Storage).
  pdfSrc: '/api/pdf/astronomy-2e',
};
