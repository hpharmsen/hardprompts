# Beslissingen

Afwegingen die definitief zijn. Een volgende `/hp:code-review` hoeft deze niet opnieuw voor
te leggen; wat op de "Nog te doen"-lijst van `latest.md` staat hoort hier juist **niet**.

- `httpx` blijft expliciet in `pyproject.toml` staan, ook al is het óók een directe dependency
  van justai. Een dependency die je zelf importeert (`modelspecs.py`) hoor je zelf te
  declareren; leunen op een transitieve dep is een tijdbom als justai ooit van HTTP-client
  wisselt. Geen reductie. (2026-07-25)
- `pyyaml` blijft. `data/models.yaml` wordt óók door de JS-kant van `visualize.html` geparseerd;
  het formaat vervangen door een platte tekstlijst is een formaatbeslissing over twee
  consumers, geen code-reductie. (2026-07-25)
- Zowel `run_jobs_sequentially` als `run_jobs_concurrently` blijven bestaan (richting A bij
  finding 2.1, gekozen door HP). Het sequentiële pad moet sequentieel én ongeshuffled blijven
  zodat je een run stap voor stap kunt volgen; de duplicatie is opgelost met gedeelde helpers
  in plaats van door het pad te schrappen. Stel richting B niet opnieuw voor. (2026-07-25)
- `run.py` houdt zijn eigen `TimeoutException`, los van justai's gelijknamige exceptie. Die van
  ons wordt door de SIGALRM-handler gegooid; justai's staat in `basemodel.py:40` en wordt hier
  bewust niet geïmporteerd. Er staat nu een comment bij dat vastlegt dat het toevoegen aan de
  import op regel 9 dit stil zou breken. (2026-07-25)
- Het verschil tussen de twee backoff-callsites blijft expliciet: de hoofdloop checkt eerst op
  quota-uitputting en gooit het model uit de run, de reviewer-loop niet. Een reviewer-ratelimit
  zegt niets over het model dat getest wordt. `backoff_or_give_up` dekt alleen het
  wachten-en-opgeven, niet die beslissing. (2026-07-25)
- "Het resultaat van meerdere passes" is het **gemiddelde per pass**, niet de som en niet de
  laatste (finding 5.4, gekozen door HP). `Storage.read` geeft bij wisselende resultaten dus
  het gemiddelde terug, en `print_results` vermenigvuldigt dat weer met het aantal passes voor
  het rijtotaal. Eén scoreregel voor alle resultaattypen: `pass_score()` in `storage.py`
  (`'√'` = 1, cijferstring = eigen waarde, rest 0), gedeeld met `get_last_n`. Gevolg: een
  gemengde `√`/`X`-cel toont een fractie (`0.666`) in plaats van een telling (`2`); dat is de
  bedoeling, want de cel toont per-pass-scores. Stel som of laatste niet opnieuw voor. (2026-07-25)
- Deze comments blijven staan; het zijn WHY's, niet herhalingen van de code:
  - `output.py` `# Read source HTML template (use template file to avoid circular reads)` —
    verklaart waarom er een aparte template-file is en niet één `visualize.html` die zichzelf
    herschrijft.
  - `output.py` `# ... using string methods` bij de EMBEDDED_DATA-replace — "using string
    methods" is de reden: `re.sub` zou backslashes in de JSON-payload als
    replacement-escapes interpreteren.
  - `run.py` `# 5, 10, 20, 40 seconds` bij `2 ** try_ * 5` — maakt de reeks in één blik leesbaar.
  - `run.py` `# Retryable server errors (504, 503, 500, overloaded, etc.)` — documenteert de
    intentie van de lijst eronder.
  - `run.py` `# Check if it's quota exhaustion (won't resolve by waiting)` — het "won't resolve
    by waiting" is de WHY achter het niet-retryen.
  - `run.py` `# Don't store result for skipped runs` (2×) — verklaren een kale `continue`/`return`.
  - `data/models.yaml` `# kimi-k2-thinking is only on OpenRouter, not on api.moonshot.ai
    (returns 404)` — externe kennis die nergens anders terug te vinden is.
  (2026-07-25)
