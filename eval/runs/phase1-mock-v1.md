# Eval Run Card — v1.jsonl

- **Run timestamp (UTC):** 2026-05-28T02:29:08+00:00
- **API base:** `http://localhost:8000`
- **Model reported by API:** `mock`
- **Golden set:** `eval/golden/v1.jsonl`
- **Questions:** 8
- **Errors:** 0

## Overall

| Metric | Value |
|---|---|
| Avg keyword score | **19.79%** |
| Avg citation accuracy | **0.00%** |
| Avg latency (ms) | 1691 |

## Per-bucket

| Bucket | N | Keyword | Citation |
|---|---|---|---|
| factual | 5 | 15.00% | 0.00% |
| chapter_scoped | 1 | 33.33% | 0.00% |
| cross_topic | 1 | 16.67% | 0.00% |
| figure_or_diagram | 1 | 33.33% | 0.00% |

## Per-question detail

### astro-001 — `factual`

**Q:** Whose Mars observation data did Kepler use to derive his laws of planetary motion, and why was that data essential?

- Keyword score: **50.00%** (matched: ['Mars', 'data']; missed: ['Tycho Brahe', 'ellipse'])
- Citation: **0.00%** (in_range=0, out_of_range=3, book_match=True)
- Latency: 1623 ms

> Based on the retrieved sources, here is a synthesized answer to the question "Whose Mars observation data did Kepler use to derive his laws of planetary motion, and why was that data essential?".  Through his analysis of the motions of the planets, Kepler developed a series of principles, now known as Kepler's three laws, which described the behavior of planets based on thei... [1] [2] [3]  Thi…

### astro-002 — `factual`

**Q:** How did Kepler discover his third law, and what relationship does it describe?

- Keyword score: **0.00%** (matched: []; missed: ['orbital period', 'semimajor axis', 'proportional', 'square', 'cube'])
- Citation: **0.00%** (in_range=0, out_of_range=3, book_match=True)
- Latency: 1473 ms

> Based on the retrieved sources, here is a synthesized answer to the question "How did Kepler discover his third law, and what relationship does it describe?".  Through his analysis of the motions of the planets, Kepler developed a series of principles, now known as Kepler's three laws, which described the behavior of planets based on thei... [1] [2] [3]  This is a mock response; swap RETRIEVAL_…

### astro-003 — `factual`

**Q:** What was Newton's central insight about Earth's gravity that allowed him to develop the universal law of gravitation?

- Keyword score: **25.00%** (matched: ['universal']; missed: ['Moon', 'inverse square', 'all bodies'])
- Citation: **0.00%** (in_range=0, out_of_range=3, book_match=True)
- Latency: 1577 ms

> Based on the retrieved sources, here is a synthesized answer to the question "What was Newton's central insight about Earth's gravity that allowed him to develop the universal law of gravitation?".  Through his analysis of the motions of the planets, Kepler developed a series of principles, now known as Kepler's three laws, which described the behavior of planets based on thei... [1] [2] [3]  T…

### astro-004 — `chapter_scoped`

**Q:** In Chapter 3, how do Kepler's three laws of planetary motion lay the foundation that Newton's universal law of gravitation later extends, and what does Newton's reformulation of Kepler's third law add?

- Keyword score: **33.33%** (matched: ['Kepler', 'Newton']; missed: ['ellipse', 'orbital period', 'inverse square', 'mass'])
- Citation: **0.00%** (in_range=0, out_of_range=3, book_match=True)
- Latency: 1870 ms

> Based on the retrieved sources, here is a synthesized answer to the question "In Chapter 3, how do Kepler's three laws of planetary motion lay the foundation that Newton's universal law of gravitation later extends, and what does Newton's reformulation of Kepler's third law add?".  Through his analysis of the motions of the planets, Kepler developed a series of principles, now known as Kepler's…

### astro-005 — `factual`

**Q:** How was Neptune discovered, and why is it described as 'the first planet discovered through mathematics'?

- Keyword score: **0.00%** (matched: []; missed: ['Adams', 'Le Verrier', 'Uranus', 'perturbations', 'predicted', '1846'])
- Citation: **0.00%** (in_range=0, out_of_range=3, book_match=True)
- Latency: 1535 ms

> Based on the retrieved sources, here is a synthesized answer to the question "How was Neptune discovered, and why is it described as 'the first planet discovered through mathematics'?".  Through his analysis of the motions of the planets, Kepler developed a series of principles, now known as Kepler's three laws, which described the behavior of planets based on thei... [1] [2] [3]  This is a moc…

### astro-006 — `cross_topic`

**Q:** How does the redshift concept (introduced earlier in the textbook in the chapter on radiation and spectra) relate to Slipher's and Hubble's later observations of distant galaxies?

- Keyword score: **16.67%** (matched: ['redshift']; missed: ['Doppler', 'wavelength', 'moving away', 'spiral', 'expanding'])
- Citation: **0.00%** (in_range=0, out_of_range=3, book_match=True)
- Latency: 1770 ms

> Based on the retrieved sources, here is a synthesized answer to the question "How does the redshift concept (introduced earlier in the textbook in the chapter on radiation and spectra) relate to Slipher's and Hubble's later observations of distant galaxies?".  Through his analysis of the motions of the planets, Kepler developed a series of principles, now known as Kepler's three laws, which des…

### astro-007 — `factual`

**Q:** What surprising pattern did Vesto Slipher find when he photographed the spectra of more than 40 spiral nebulae, and why did he have to expose photographic plates for 20 to 40 hours?

- Keyword score: **0.00%** (matched: []; missed: ['redshift', 'moving away', '1800 kilometers', 'faint', 'long exposure'])
- Citation: **0.00%** (in_range=0, out_of_range=3, book_match=True)
- Latency: 1867 ms

> Based on the retrieved sources, here is a synthesized answer to the question "What surprising pattern did Vesto Slipher find when he photographed the spectra of more than 40 spiral nebulae, and why did he have to expose photographic plates for 20 to 40 hours?".  Through his analysis of the motions of the planets, Kepler developed a series of principles, now known as Kepler's three laws, which d…

### astro-008 — `figure_or_diagram`

**Q:** Describe what an H-R diagram (Hertzsprung-Russell diagram) shows: what are its two axes, who created it, and what does the location of a star on the diagram tell you?

- Keyword score: **33.33%** (matched: ['Hertzsprung', 'Russell']; missed: ['luminosity', 'temperature', 'spectral', 'main sequence'])
- Citation: **0.00%** (in_range=0, out_of_range=3, book_match=True)
- Latency: 1810 ms

> Based on the retrieved sources, here is a synthesized answer to the question "Describe what an H-R diagram (Hertzsprung-Russell diagram) shows: what are its two axes, who created it, and what does the location of a star on the diagram tell you?".  Through his analysis of the motions of the planets, Kepler developed a series of principles, now known as Kepler's three laws, which described the be…

