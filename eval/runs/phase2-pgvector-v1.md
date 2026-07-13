# Eval Run Card — v1.jsonl

- **Run timestamp (UTC):** 2026-07-13T03:47:07+00:00
- **API base:** `http://localhost:8000`
- **Model reported by API:** `gemini-2.5-flash`
- **Golden set:** `/Users/ankiyang/projects/rag-docs-search/eval/golden/v1.jsonl`
- **Questions:** 8
- **Errors:** 0

## Overall

| Metric | Value |
|---|---|
| Avg keyword score | **86.46%** |
| Avg citation accuracy | **57.50%** |
| Avg latency (ms) | 19564 |

## Per-bucket

| Bucket | N | Keyword | Citation |
|---|---|---|---|
| factual | 5 | 85.00% | 60.00% |
| chapter_scoped | 1 | 66.67% | 80.00% |
| cross_topic | 1 | 100.00% | 60.00% |
| figure_or_diagram | 1 | 100.00% | 20.00% |

## Per-question detail

### astro-001 — `factual`

**Q:** Whose Mars observation data did Kepler use to derive his laws of planetary motion, and why was that data essential?

- Keyword score: **100.00%** (matched: ['Tycho Brahe', 'Mars', 'data', 'ellipse']; missed: [])
- Citation: **60.00%** (in_range=3, out_of_range=2, book_match=True)
- Latency: 19593 ms

> Kepler used Tycho Brahe's observations of Mars to derive his laws of planetary motion [1, 3]. This data was essential because Kepler's initial assumption that planetary orbits were circles was inconsistent with Brahe's observations [2]. Working with Brahe's data, Kepler discovered that the orbit of Mars was a flattened circle, or ellipse, which was critical for understanding planetary motions […

### astro-002 — `factual`

**Q:** How did Kepler discover his third law, and what relationship does it describe?

- Keyword score: **100.00%** (matched: ['orbital period', 'semimajor axis', 'proportional', 'square', 'cube']; missed: [])
- Citation: **60.00%** (in_range=3, out_of_range=2, book_match=True)
- Latency: 17845 ms

> Kepler discovered his third law in 1619, after many years of working to find mathematical patterns in planetary movements and seeking a "harmony of the spheres" [1]. He used the accurate observations of planetary positions collected by Tycho Brahe [2]. Kepler gained full access to Brahe's "priceless records" after Brahe's death in 1601, and the study of these records occupied him for over 20 ye…

### astro-003 — `factual`

**Q:** What was Newton's central insight about Earth's gravity that allowed him to develop the universal law of gravitation?

- Keyword score: **25.00%** (matched: ['Moon']; missed: ['universal', 'inverse square', 'all bodies'])
- Citation: **80.00%** (in_range=4, out_of_range=1, book_match=True)
- Latency: 9724 ms

> Newton's central insight was that Earth's gravity might extend beyond its surface, specifically as far as the Moon, to produce the force necessary to keep the Moon in its orbit by curving its path from a straight line [1]. He further hypothesized that gravity is not limited to Earth but is a general force of attraction between all material bodies [1]. This idea suggested that the attractive for…

### astro-004 — `chapter_scoped`

**Q:** In Chapter 3, how do Kepler's three laws of planetary motion lay the foundation that Newton's universal law of gravitation later extends, and what does Newton's reformulation of Kepler's third law add?

- Keyword score: **66.67%** (matched: ['orbital period', 'mass', 'Kepler', 'Newton']; missed: ['ellipse', 'inverse square'])
- Citation: **80.00%** (in_range=4, out_of_range=1, book_match=True)
- Latency: 25797 ms

> Kepler's three laws of planetary motion laid the foundation for Newton's universal law of gravitation by providing a precise geometric description of how planets move, which Newton then sought to explain [3, 4]. Kepler's laws described the elliptical orbits of planets, the equal areas swept out by a planet-Sun line, and the relationship between a planet's orbital period and its distance from th…

### astro-005 — `factual`

**Q:** How was Neptune discovered, and why is it described as 'the first planet discovered through mathematics'?

- Keyword score: **100.00%** (matched: ['Adams', 'Le Verrier', 'Uranus', 'perturbations', 'predicted', '1846']; missed: [])
- Citation: **60.00%** (in_range=3, out_of_range=2, book_match=True)
- Latency: 17891 ms

> Neptune was discovered through mathematical prediction based on irregularities in the orbit of Uranus [1, 3, 5]. Astronomers had long suspected its existence due to the "disobedient" motion of Uranus [1].  In 1843, John Couch Adams began a detailed mathematical analysis of these irregularities, hypothesizing an unknown planet more distant than Uranus and determining its necessary mass and orbit…

### astro-006 — `cross_topic`

**Q:** How does the redshift concept (introduced earlier in the textbook in the chapter on radiation and spectra) relate to Slipher's and Hubble's later observations of distant galaxies?

- Keyword score: **100.00%** (matched: ['Doppler', 'wavelength', 'moving away', 'redshift', 'spiral', 'expanding']; missed: [])
- Citation: **60.00%** (in_range=3, out_of_range=2, book_match=True)
- Latency: 20369 ms

> Redshift, a concept introduced earlier in the textbook, refers to the displacement of spectral lines toward longer wavelengths (the red end of the visible spectrum), which indicates that the source of the waves is moving away from the observer [1].  Vesto M. Slipher applied this concept in his observations of spiral nebulae (which were later identified as galaxies) [1]. Beginning in 1912, Sliph…

### astro-007 — `factual`

**Q:** What surprising pattern did Vesto Slipher find when he photographed the spectra of more than 40 spiral nebulae, and why did he have to expose photographic plates for 20 to 40 hours?

- Keyword score: **100.00%** (matched: ['redshift', 'moving away', '1800 kilometers', 'faint', 'long exposure']; missed: [])
- Citation: **40.00%** (in_range=2, out_of_range=3, book_match=True)
- Latency: 16830 ms

> When Vesto Slipher photographed the spectra of more than 40 spiral nebulae, he found that the spectral lines of most galaxies showed an astounding redshift, meaning the lines were displaced toward longer wavelengths [1]. This indicated that most spirals were racing away from Earth at high speeds, with the highest velocity he measured being 1800 kilometers per second [1]. Only a few spirals, suc…

### astro-008 — `figure_or_diagram`

**Q:** Describe what an H-R diagram (Hertzsprung-Russell diagram) shows: what are its two axes, who created it, and what does the location of a star on the diagram tell you?

- Keyword score: **100.00%** (matched: ['luminosity', 'temperature', 'spectral', 'Hertzsprung', 'Russell', 'main sequence']; missed: [])
- Citation: **20.00%** (in_range=1, out_of_range=4, book_match=True)
- Latency: 28465 ms

> A Hertzsprung-Russell (H-R) diagram is a fundamental tool in astronomy used for classifying stars and understanding stellar evolution [2, 3, 4, 5]. It summarizes how a star or protostar changes over time [5].  **Axes:** *   **Y-axis:** Represents the star's luminosity, often relative to the Sun's luminosity (L_Sun), indicating its intrinsic brightness. Luminosity is plotted along the vertical a…

