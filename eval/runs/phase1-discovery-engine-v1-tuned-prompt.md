# Eval Run Card — v1.jsonl

- **Run timestamp (UTC):** 2026-06-09T12:43:30+00:00
- **API base:** `http://localhost:8000`
- **Model reported by API:** `gemini-2.5-flash`
- **Golden set:** `eval/golden/v1.jsonl`
- **Questions:** 8
- **Errors:** 0

## Overall

| Metric | Value |
|---|---|
| Avg keyword score | **18.54%** |
| Avg citation accuracy | **0.00%** |
| Avg latency (ms) | 3574 |

## Per-bucket

| Bucket | N | Keyword | Citation |
|---|---|---|---|
| factual | 5 | 23.00% | 0.00% |
| chapter_scoped | 1 | 16.67% | 0.00% |
| cross_topic | 1 | 16.67% | 0.00% |
| figure_or_diagram | 1 | 0.00% | 0.00% |

## Per-question detail

### astro-001 — `factual`

**Q:** Whose Mars observation data did Kepler use to derive his laws of planetary motion, and why was that data essential?

- Keyword score: **50.00%** (matched: ['Mars', 'data']; missed: ['Tycho Brahe', 'ellipse'])
- Citation: **0.00%** (in_range=0, out_of_range=1, book_match=False)
- Latency: 5695 ms

> Kepler used data for Mars to analyze the motions of the planets and derive his laws [1]. However, the provided context does not specify whose Mars observation data Kepler used, nor does it explicitly state why that data was essential beyond its use in deriving his laws [1].  Access for free at openstax.org

### astro-002 — `factual`

**Q:** How did Kepler discover his third law, and what relationship does it describe?

- Keyword score: **40.00%** (matched: ['orbital period', 'square']; missed: ['semimajor axis', 'proportional', 'cube'])
- Citation: **0.00%** (in_range=0, out_of_range=1, book_match=False)
- Latency: 3814 ms

> Kepler's third law describes a relationship where a planet's orbital period squared is equal to its average distance from the Sun [1]. The provided context does not explain how Kepler discovered this law.  Access for free at openstax.org

### astro-003 — `factual`

**Q:** What was Newton's central insight about Earth's gravity that allowed him to develop the universal law of gravitation?

- Keyword score: **25.00%** (matched: ['universal']; missed: ['Moon', 'inverse square', 'all bodies'])
- Citation: **0.00%** (in_range=0, out_of_range=1, book_match=False)
- Latency: 3965 ms

> I don't find this in the sources. The provided context mentions Newton's universal law of gravitation and the gravitational constant, but it does not describe Newton's central insight about Earth's gravity that led to its development [1].  Access for free at openstax.org

### astro-004 — `chapter_scoped`

**Q:** In Chapter 3, how do Kepler's three laws of planetary motion lay the foundation that Newton's universal law of gravitation later extends, and what does Newton's reformulation of Kepler's third law add?

- Keyword score: **16.67%** (matched: ['Kepler']; missed: ['ellipse', 'orbital period', 'inverse square', 'mass', 'Newton'])
- Citation: **0.00%** (in_range=0, out_of_range=1, book_match=False)
- Latency: 2242 ms

> I don't find this in the sources. The provided context briefly mentions Kepler's three fundamental laws of planetary motion and that they describe the behavior of planets in their orbits [1].  Access for free at openstax.org

### astro-005 — `factual`

**Q:** How was Neptune discovered, and why is it described as 'the first planet discovered through mathematics'?

- Keyword score: **0.00%** (matched: []; missed: ['Adams', 'Le Verrier', 'Uranus', 'perturbations', 'predicted', '1846'])
- Citation: **0.00%** (in_range=0, out_of_range=1, book_match=False)
- Latency: 2698 ms

> Neptune was discovered with a telescope [1].  The provided context mentions the discovery of Neptune and that it was found using a telescope, but it does not explain how mathematics contributed to its discovery or why it is described as 'the first planet discovered through mathematics' [1].  Access for free at openstax.org

### astro-006 — `cross_topic`

**Q:** How does the redshift concept (introduced earlier in the textbook in the chapter on radiation and spectra) relate to Slipher's and Hubble's later observations of distant galaxies?

- Keyword score: **16.67%** (matched: ['redshift']; missed: ['Doppler', 'wavelength', 'moving away', 'spiral', 'expanding'])
- Citation: **0.00%** (in_range=0, out_of_range=1, book_match=False)
- Latency: 3810 ms

> I don't find this in the sources. The provided context mentions "Radiation and Spectra" and the ability to "calculate the radial velocity of the star" or "galaxy" [1]. However, it does not discuss the redshift concept or its relation to Slipher's and Hubble's observations of distant galaxies.  Access for free at openstax.org

### astro-007 — `factual`

**Q:** What surprising pattern did Vesto Slipher find when he photographed the spectra of more than 40 spiral nebulae, and why did he have to expose photographic plates for 20 to 40 hours?

- Keyword score: **0.00%** (matched: []; missed: ['redshift', 'moving away', '1800 kilometers', 'faint', 'long exposure'])
- Citation: **0.00%** (in_range=0, out_of_range=1, book_match=False)
- Latency: 2476 ms

> I don't find this in the sources. The provided context discusses astronauts capturing an orbiting telescope and installing a package [1].  Access for free at openstax.org

### astro-008 — `figure_or_diagram`

**Q:** Describe what an H-R diagram (Hertzsprung-Russell diagram) shows: what are its two axes, who created it, and what does the location of a star on the diagram tell you?

- Keyword score: **0.00%** (matched: []; missed: ['luminosity', 'temperature', 'spectral', 'Hertzsprung', 'Russell', 'main sequence'])
- Citation: **0.00%** (in_range=0, out_of_range=1, book_match=False)
- Latency: 3890 ms

> I don't find this in the sources. The provided context appears to be a snippet from a textbook's question or index, mentioning diagrams and star locations in a general sense, but not specifically the H-R diagram or its characteristics [1].  Access for free at openstax.org

