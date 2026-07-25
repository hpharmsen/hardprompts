# Code Review — 2026-07-25 /Users/hp/proj/hardprompts

Scope: `main.py`, `run.py`, `output.py`, `storage.py`, `modelspecs.py` (5 files, ~660 regels).
Geen `docs/code-reviews/decisions.md` aanwezig: dit is de eerste run.

**Geen testsuite in dit project** (`tests/` bestaat niet). De verificatie-gate valt daarmee
terug op ruff + import-smoke + entrypoint-smoke. Gedragswijzigingen zijn daardoor niet
automatisch te verifiëren; dat is meegewogen in de labels.

## Samenvatting
- Totaal findings: 19 (SAFE: 13, LIKELY: 6, RISKY: 0) — 5.4 kwam er tijdens de fix-pass bij
- Toegepast: 18 (alle 13 SAFE + alle 5 LIKELY uit de interactieve ronde), 1 open (5.4)
- Netto regels: -43 (SAFE) en +20 (LIKELY, waar 5.2 en 5.3 bewust code toevoegen)
- Twee gedragsdefecten gevonden en gefixt (5.2, 5.3), één gevonden en open (5.4)

## Bijvangst

- **5.2** — een justai `ConnectionException`, `AuthorizationException`, `ModelOverloadException`,
  `TimeoutException` of `RefusalException` op poging 1 t/m 4 matcht geen van de vier outer
  handlers in `run_prompt`, ontsnapt uit de functie, en breekt de **hele benchmark-run** af.
  Beide paden: sequentieel vangt alleen de eigen `TimeoutException`, concurrent gebruikt
  `asyncio.gather` zonder `return_exceptions=True`. Geen reductie, wel het echte probleem
  in deze codebase.
- **5.3** — `max_score` (net toegevoegd aan VERSCHILLEN1/2) wordt wél gelezen door
  `visualize_template.html:558` maar niet door `print_report`. Die berekent
  `max_correct = passes * len(test_names)`, dus max 1 per test, terwijl `get_last_n` voor
  VERSCHILLEN1 tot 12 optelt. De terminal-rapportage toont daardoor totalen boven het
  maximum (bijv. `41/18`); de HTML-visualisatie klopt wel.

## 1. Zware dependencies (0 findings)

Geen. `httpx` staat expliciet in `pyproject.toml` en is óók een directe dependency van
justai — expliciet declareren is hier juist correct, niet dubbel. `pyyaml` leest een
datafile die de JS-kant van `visualize.html` ook parseert; die vervangen is een
formaatbeslissing, geen reductie.

## 2. Duplicate code / DRY (LIKELY: 2)

### Finding 2.1 [LIKELY] — `run_jobs_sequentially` vs `run_job_async` in run.py:64-98 / 122-151
- Regels bespaard: ~35 (richting B) of ~15 (richting A)
- Twee functies met bijna regel-voor-regel dezelfde body: dezelfde job-unpack, dezelfde
  skip-check op `skipped_models`, dezelfde `logging.info`, hetzelfde banner-`print` met
  dezelfde `"*" * (32 - len(...))`-berekening, dezelfde timeout-fallback naar `'T'`,
  dezelfde `storage.add` + afsluitende `logging.info`. Alleen het timeout-mechanisme
  verschilt (`signal.alarm` vs `asyncio.wait_for`).
- Richting A: shared helpers extraheren (banner + skip-check, en de store-stap).
- Richting B: `run_jobs_sequentially`, `TimeoutException`, `timeout_handler` en de
  `signal`-import schrappen, en niet-concurrent draaien als de async-pad met
  `Semaphore(1)`.
- **Waarom LIKELY**: richting B verandert gedrag op een pad zonder tests — `shuffle(jobs)`
  gebeurt nu alleen in het concurrent-pad, dus de sequentiële volgorde wordt willekeurig,
  en elke prompt loopt dan via `asyncio.to_thread` in plaats van op de hoofdthread. De
  keuze tussen A en B is ontwerp, geen feit.

### Finding 2.2 [LIKELY] — retry-met-backoff twee keer uitgeschreven in run.py:221-235 / 240-256
- Regels bespaard: ~12
- Huidig: de rate-limit-tak van de hoofdloop en de reviewer-loop doen allebei
  `wait = 2 ** try * 5`, `logging.warning`, `print(YELLOW, ...)`, `if try == 4: return 'R'`,
  `time.sleep(wait)`.
- Voorstel: één helper `retry_with_backoff(...)` of een generator die de wachttijden levert
  en op de vijfde poging `'R'` teruggeeft.
- **Waarom LIKELY**: de twee loops verschillen subtiel — de hoofdloop checkt eerst op
  quota-uitputting en geeft dan `(None, None, reason)` terug om het model te skippen, de
  reviewer-loop doet dat niet. Een helper die dat verschil platslaat verandert wanneer een
  model uit de run valt, en dat pad raakt geen enkele test.

## 3. Speculatieve abstracties / YAGNI (LIKELY: 1)

### Finding 3.1 [LIKELY] — `Storage.add` herschrijft het hele bestand per resultaat, storage.py:40-56
- Regels bespaard: ~10
- Huidig: `add` doet `_read_all()` (1972 regels JSON parsen), append in memory, dan
  `_write_all()` (1972 regels serialiseren). Per opgeslagen resultaat. Bij ~30 modellen ×
  ~18 prompts is dat 540 volledige rewrites in één run, oplopend naar 2500 regels: O(n²)
  werk voor een append-only logbestand.
- Voorstel: `add` opent met `'a'` en schrijft één regel. `_write_all` wordt daarmee dood
  (zie 4.x-afhankelijkheid) en de parse-stap verdwijnt.
- **Waarom LIKELY**: `_write_all` is vandaag de enige writer, dus de rewrite is nu een
  impliciete atomicity-garantie — breekt een run halverwege een write af, dan staat er nu
  nog het vorige complete bestand, en na de wijziging mogelijk een halve regel die
  `_read_all` laat crashen op `json.loads`. Klein risico op een pad zonder tests, en de
  keuze (puur append vs. append + tolerante reader) is ontwerp.

## 4. Dode code (SAFE: 3)

### Finding 4.1 [SAFE] — `Storage.reset` in storage.py:86-91
- Regels bespaard: 7
- Bewijs, nul aanroepers, ook niet als string-literal:
  ```bash
  git grep -n "reset"    # → alleen storage.py:86, de definitie zelf
  ```
  De repo bevat geen `getattr`/`setattr`/`importlib`/`eval`/`exec`/`globals`, dus er is geen
  enkel pad waarlangs deze naam dynamisch geraakt kan worden.
- Actie: methode verwijderen.

### Finding 4.2 [SAFE] — ongebruikte imports in run.py:5-6
- Regels bespaard: 0 (edits in plaats)
- `random.random` (F401) en `typing.Set` (F401). Geen `__init__.py`, geen re-export.
- Actie: `from random import shuffle` en `from typing import List, Dict, Tuple`.

### Finding 4.3 [SAFE] — ongebruikte derde return van `Storage.get_last_n`, storage.py:93-117
- Regels bespaard: 3
- Huidig: `total` wordt opgeteld (`total = 0`, `total += len(records)`) en teruggegeven,
  maar de enige aanroeper gooit hem weg: `correct, avg_duration, _ = storage.get_last_n(...)`
  in output.py:72.
- Bewijs: `git grep -n "get_last_n"` → alleen de definitie en die ene aanroep; geen
  string-literal hits.
- Actie: `total` schrappen, return naar een 2-tuple, aanroeper aanpassen.

## 5. Ontbrekende / overbodige guards (SAFE: 1, LIKELY: 2)

### Finding 5.1 [SAFE] — dubbele existence-check in `Storage._read_all`, storage.py:25-26
- Regels bespaard: 2
- Huidig:
  ```python
  if not os.path.exists(self.filename) or os.path.getsize(self.filename) == 0:
      return []
  ```
- `__init__` (regel 19-21) maakt het bestand aan als het niet bestaat, dus `exists` kan hier
  niet False zijn. En een leeg bestand levert al `[]` op uit de list-comprehension eronder,
  dus de `getsize`-tak is ook overbodig.
- Actie: het hele `if` weghalen.

### Finding 5.2 [LIKELY] — niet-afgevangen justai-excepties breken de run af, run.py:200
- Regels bespaard: **-6** (dit is een fix, geen reductie; niet meegeteld in het totaal)
- Huidig: de binnenste `except Exception as e` doet op poging 1-4 `raise e`, waarna vier
  outer handlers klaarstaan: `NotImplementedError`, `BadRequestException`,
  `GeneralException`, `RatelimitException`. Maar justai definieert er acht, allemaal directe
  `Exception`-subclasses (`basemodel.py:25-46`): ook `ConnectionException`,
  `AuthorizationException`, `ModelOverloadException`, `TimeoutException` en
  `RefusalException`. Die matchen geen enkele handler, ontsnappen uit `run_prompt`, en
  daarmee uit `run_jobs_sequentially` (dat alleen zijn eigen `TimeoutException` vangt) of
  uit `asyncio.gather` (zonder `return_exceptions=True`) — in beide gevallen valt de hele
  benchmark om, met verlies van alle nog niet opgeslagen jobs.
  CLAUDE.md documenteert `E` als "unhandled exception after retries", dus de bedoelde guard
  bestaat op papier al; alleen het niet-laatste-poging-pad mist hem.
- Richting A: de vijf ontbrekende justai-excepties toevoegen aan import + handlers, met
  `ConnectionException`/`ModelOverloadException`/`TimeoutException` als retryable en
  `AuthorizationException`/`RefusalException` als direct-terminaal.
- Richting B: minimale variant — één `except Exception: return 'E'` als laatste outer
  handler, zodat niets meer ontsnapt zonder dat je de taxonomie uitbreidt.
- **Waarom LIKELY**: welke exceptie welke result-code verdient is een keuze over de
  taxonomie die jij net hebt uitgebreid met `G`, en die codes staan in CLAUDE.md én worden
  door `visualize.html` gelezen. Richting A is netter maar zet gedrag vast dat ik niet kan
  testen (geen testsuite, en de excepties treden alleen op bij echte API-fouten).
- **Gekozen: richting B.** Geverifieerd tegen de vorige commit: pre-fix ontsnapte een
  `ConnectionException` daadwerkelijk uit `run_prompt`, post-fix geeft die `'E'` terug.

### Finding 5.3 [LIKELY] — `print_report` negeert `max_score`, output.py:66
- Regels bespaard: **-3** (fix, niet meegeteld)
- Huidig: `max_correct = passes * len(test_names)`. `get_last_n` telt voor VERSCHILLEN1
  echter tot 12 op (`r['result'].isdigit()` → `correct += int(...)`), dus het rapport toont
  totalen boven het gerapporteerde maximum.
- `visualize_template.html:558` doet het wél goed:
  `body.match(/^max_score\s*=\s*(\d+)/m)`, default 1.
- Voorstel: `max_correct = passes * sum(tc.get('max_score', 1) for tc in test_cases.values())`.
  `print_report` heeft `test_cases` al, dus dit is één regel.
- **Waarom LIKELY**: `print_results` (de default-output, zonder `-r`) telt in dezelfde stijl
  op zonder enig maximum te tonen. De vraag of daar óók een genormaliseerde score moet
  staan is een rapportage-keuze, niet een bug-fix, en die wil ik niet stil voor je maken.

## 6. Verbose patterns (SAFE: 3)

### Finding 6.1 [SAFE] — SIM115: file handles lekken in run.py:164
- Regels bespaard: 0 (netto +1 door de import)
- Huidig: `images = [open(img, 'rb').read() for img in image_path] if image_path else None`
- Voorstel: `images = [Path(img).read_bytes() for img in image_path] if image_path else None`
  met `from pathlib import Path`. Sluit de handles deterministisch in plaats van pas bij GC;
  bij 12 gelijktijdige jobs met 2 images elk telt dat op.

### Finding 6.2 [SAFE] — SIM114: identieke if-armen in run.py:269-274
- Regels bespaard: 3
- Beide armen doen `print(GREEN, model_name, 'CORRECT', RESET)` + `passed = '√'`.
- Actie: samenvoegen met `or answer and answer == message`.

### Finding 6.3 [SAFE] — verbose loop in `get_jobs`, run.py:30-48
- Regels bespaard: 1
- `for test_name in list(test_cases.keys())` + `test_case = test_cases[test_name]` →
  `for test_name, test_case in test_cases.items()`. De `list()` was nodig als de dict tijdens
  de loop muteerde; dat gebeurt niet (alleen `test_case['name'] = test_name`, een mutatie
  ván de value, niet ván de dict).
- Idem `results += [job]` → `results.append(job)`.

## 7. Nutteloze wrappers (SAFE: 2)

### Finding 7.1 [SAFE] — `js_escape` in output.py:91-92
- Regels bespaard: 3
- Huidig:
  ```python
  def js_escape(s):
      return json.dumps(s)
  ```
  Een alias zonder toevoeging, 4 aanroepen verderop in dezelfde functie.
- Actie: `json.dumps` direct gebruiken in de f-strings.

### Finding 7.2 [SAFE] — geneste `average` in `Storage.read`, storage.py:69-70
- Regels bespaard: 2
- Een geneste `def` voor één expressie, één keer aangeroepen. Dertig regels lager, in
  `get_last_n:116`, staat exact dezelfde berekening al inline
  (`sum(durations) / len(durations) if durations else None`).
- Actie: inline zetten, consistent met `get_last_n`.

## 8. Comment-hygiëne (SAFE: 4)

### Finding 8.1 [SAFE] — storage.py docstrings herhalen de signature
- Regels bespaard: 22
- `__init__`, `add` en `read` hebben Google-style `Args:`-blokken die letterlijk de
  parameternamen en hun al-aanwezige type hints opsommen ("model (str): The model name.").
  De projectstandaard is één-regel docstrings.
- Bovendien is het `Returns:`-blok van `read` **feitelijk fout**: het documenteert
  `Tuple[Optional[str], Optional[float]]` terwijl de functie een 3-tuple teruggeeft
  (`result, duration, len(data)`) — precies waar `get_jobs` de derde waarde op leest.
- Actie: terugbrengen tot één regel per methode.

### Finding 8.2 [SAFE] — comments in storage.py die de code herhalen
- Regels bespaard: 3
- storage.py:73 `# Check if the 'result' field is '√' for each record using all()` — herhaalt
  de code én is fout: de `all()` eronder vergelijkt met `data[0]['result']`, niet met `'√'`.
- storage.py:76 `# If all records have the same 'result' field, return it` en :80
  `# else return the number of '√'` — herhalen de regel eronder.

### Finding 8.3 [SAFE] — dode en foute comments in run.py
- Regels bespaard: 3
- run.py:35-36: uitgecommentarieerde code `# if "4.1" in model and test_case.get("image"):`.
- run.py:108: `# Limit to 3 concurrent jobs` — **staat er fout**, `MAX_CONCURRENT_JOBS` is 12.
  De constante is zelf-documenterend; comment weg.
- run.py:55: `# Reset at start of run` naast `skipped_models = {}` — herhaalt de code.

### Finding 8.4 [SAFE] — WHY-comments toevoegen
- Regels bespaard: **-3** (bewuste toevoeging)
- run.py:101: vastleggen dat deze `TimeoutException` bewust een eigen class is en niet
  justai's gelijknamige exceptie — die bestaat óók (`basemodel.py:40`) en wordt hier niet
  geïmporteerd. Zet iemand hem later wel in de import op regel 9, dan breekt dit stil.
- run.py:200: uitleggen waarom `raise e` bestaat — de binnenste generieke handler doet het
  logging/classificatie-werk en gooit door zodat de outer typed handlers de justai-soort
  kunnen bepalen. Dat is de meest verwarrende constructie in de file.
- run.py:170: waarom `cached=False` — een cache-hit zou een eerder antwoord teruggeven en
  daarmee de benchmark zinloos maken.

**Comments die ik bewust laat staan** (zonder deze lijst ruimt een volgende run ze alsnog op):

- output.py:81 `# Read source HTML template (use template file to avoid circular reads)` —
  de waardevolste comment in de codebase: verklaart waarom er een aparte template-file is
  en niet één `visualize.html` die zichzelf herschrijft.
- output.py:104 `# Find and replace the empty EMBEDDED_DATA block using string methods` —
  "using string methods" is de WHY: `re.sub` zou backslashes in de JSON-payload als
  replacement-escapes interpreteren.
- run.py:228 `# 5, 10, 20, 40, 80 seconds` — maakt `2 ** try_ * 5` in één blik leesbaar.
- run.py:184 `# Retryable server errors (504, 503, 500, overloaded, etc.)` — documenteert de
  intentie van de lijst eronder.
- run.py:223 `# Check if it's quota exhaustion (won't resolve by waiting)` — het "won't
  resolve by waiting" is precies de WHY achter het niet-retryen.
- run.py:89 en :144 `# Don't store result for skipped runs` — verklaren een kale
  `continue`/`return`.
- data/models.yaml `# kimi-k2-thinking is only on OpenRouter, not on api.moonshot.ai
  (returns 404)` — externe kennis die nergens anders terug te vinden is.

## Afhankelijkheden tussen findings

- 3.1 (append-only `add`) maakt `Storage._write_all` dood. Wordt 3.1 toegepast, verwijder
  dan `_write_all` in dezelfde pass; die regels zijn niet apart geteld.
- 5.1 raakt `_read_all`, 3.1 raakt `add`. Onafhankelijk, geen conflict.
- 4.1 (`reset` weg) maakt een aparte opruiming van de overbodige
  `if os.path.exists: os.remove` binnen `reset` zinloos: die vervalt met 4.1 en is niet
  apart geteld.

## Nieuw gevonden tijdens de fix-pass

### Finding 5.4 [LIKELY] — `Storage.read` geeft altijd `'0'` voor multi-answer prompts, storage.py:44-52
- **Nog niet gefixt**, gevonden bij het verifiëren van 5.3.
- Bij VERSCHILLEN1/2 slaat `run_prompt` de reviewer-score op als cijferstring
  (`passed = str(message['aantal_goed'])`, dus `'7'`, `'4'`, …). Krijgen meerdere passes een
  verschillende score, dan valt `read` in de else-tak:
  ```python
  result = str(len([record for record in data if record['result'] == '√']))
  ```
  Die telt `'√'`-records, en die zijn er bij zo'n prompt per definitie nul. Uitkomst: `'0'`.
- Bewijs uit de echte data:
  ```
  gpt-5.6-luna    VERSCHILLEN1  opgeslagen: '7', '9', '5'          -> read() geeft '0'
  claude-opus-4-5 VERSCHILLEN1  opgeslagen: '3','4','4','4','4'    -> read() geeft '0'
  ```
- `print_results` toont daardoor 0 voor elke multi-answer prompt met wisselende scores. Raakt
  **niet** `print_report` (die gebruikt `get_last_n`, dat correct optelt) en **niet** de
  HTML-visualisatie (die parseert `results.jsonl` zelf in JS).
- Voorstel: in de else-tak het gemiddelde of de som van de cijferscores nemen in plaats van
  `'√'` te tellen.
- **Waarom LIKELY**: `read` levert ook `model_passes` aan `get_jobs` voor de cache-beslissing
  (`_, _, model_passes = storage.read(...)`, run.py:35). Die derde waarde raak ik niet, maar
  de semantiek van de eerste waarde veranderen is een keuze over wat "het resultaat" van
  meerdere passes betekent: gemiddelde, som, of laatste. Dat is jouw definitie.

## Applied-log (Modus 1, SAFE-set)

Baseline vóór de eerste wijziging:

| Gate-stap | Baseline | Na SAFE-set |
|---|---|---|
| `ruff check --select F,E9 .` | **3 errors** (F401 ×2 run.py:5-6, F541 run.py:250) | **All checks passed** |
| `ruff check --select F401,F841,C4,SIM .` | 4 findings | **All checks passed** |
| Framework-check | n.v.t. (geen Django) | n.v.t. |
| Testsuite | **afwezig** (`tests/` bestaat niet) | afwezig |
| Import-smoke (5 modules) | 5/5 ok | 5/5 ok |
| Entrypoint-smoke | arg-parsing + `print_report` ok | idem, byte-identieke output |

| Finding | Status | Wat er gebeurde |
|---|---|---|
| 4.1 `Storage.reset` dood | `applied` | Methode verwijderd (storage.py), -7 regels |
| 4.2 F401 ×2 | `applied` | `random.random` en `typing.Set` uit de imports |
| 4.3 `get_last_n` third return | `applied` | `total` weg, return is nu 2-tuple; aanroeper output.py:72 aangepast |
| 5.1 dubbele existence-check | `applied` | `if not exists or getsize == 0` uit `_read_all` |
| 6.1 SIM115 fd-leak | `applied` | `open(img,'rb').read()` → `Path(img).read_bytes()`, `pathlib`-import erbij |
| 6.2 SIM114 identieke armen | `applied` | Armen samengevoegd; equivalentie geverifieerd op 9 input-combinaties |
| 6.3 verbose loop `get_jobs` | `applied` | `.items()` + `.append()`; geverifieerd met cache aan (0 jobs) en uit (160 jobs) |
| 7.1 `js_escape` alias | `applied` | `json.dumps` direct; gegenereerde `visualize.html` is **byte-identiek** aan daarvoor |
| 7.2 geneste `average` | `applied` | Inline gezet, consistent met `get_last_n` |
| 8.1 storage.py docstrings | `applied` | 3 Args/Returns-blokken → één regel; het foute `Returns`-blok van `read` is daarmee weg |
| 8.2 storage.py comments | `applied` | Foute `'√'`-comment weg, 2 herhalende comments weg, 1 vervangen door een WHY |
| 8.3 run.py comments | `applied` | Uitgecommentarieerde code weg, foute "Limit to 3 concurrent jobs" weg, `# Reset at start of run` weg |
| 8.4 WHY-comments toevoegen | `applied` | 3 comments erbij (TimeoutException-collision, `raise e`-flow, `cached=False`) |
| — F541 (bijvangst uit de gate) | `applied` | `f'REVIEWER RATE LIMITED after 5 attempts'` had geen placeholders; stond al rood in de baseline |

Netto: **-73 / +30 regels** over `run.py`, `output.py`, `storage.py` (43 regels minder).
Een `uv.lock`-wijziging die `uv run` zelf veroorzaakte is teruggedraaid; die hoort niet bij deze review.

## Applied-log (Modus 1, LIKELY-set)

Alle vijf LIKELY-findings kregen "fixen" in de interactieve ronde. Zelfde baseline als
hierboven.

| Finding | Keuze | Status | Wat er gebeurde |
|---|---|---|---|
| 5.2 excepties | Richting B: vangnet-except | `applied` | `except Exception: return 'E'` als laatste outer handler in `run_prompt`, met WHY-comment die de vijf justai-excepties benoemt |
| 2.1 job-runners | Richting A: helpers extraheren | `applied` | `start_job`, `report_timeout`, `finish_job` erbij; beide runners gebruiken ze. Sequentieel blijft sequentieel en ongeshuffled |
| 2.2 backoff | Fixen | `applied` | `backoff_or_give_up(label, try_, error)`; het quota-skip-verschil staat expliciet in beide callsites, met comment bij de reviewer-loop |
| 3.1 storage | Fixen + tolerante reader | `applied` | `add` opent met `'a'` en schrijft één regel; `_write_all` verwijderd; `_read_all` slaat een onvolledige regel over |
| 5.3 max_score | Beide rapportages | `applied` | `max_score()` helper; `print_report` gebruikt `passes * max_score(...)`; `print_results` telt per model `max_score × opgeslagen passes` op |

**Correctie tijdens de pass**: mijn eerste versie van `print_results` gebruikte één vlakke
`max_score(test_cases)` als noemer, wat `8/4` opleverde. `correct` telt daar over álle
opgeslagen passes, dus de noemer moet `max_score × aantal passes` per model zijn. Rechtgezet
vóór de gate.

Gate-uitkomst na de LIKELY-set (zelfde baseline: ruff 3 errors, geen testsuite):

| Gate-stap | Uitkomst |
|---|---|
| `ruff check --select F,E9 .` | All checks passed |
| `ruff check --select F401,F841,C4,SIM .` | All checks passed |
| Framework-check | n.v.t. |
| Testsuite | afwezig — vervangen door een functionele verificatie van de vijf gewijzigde paden: **34/34 checks** (append-only, truncated-line recovery, read-aggregatie, beide runners end-to-end incl. skip_reason, backoff-reeks 5/10/20/40, alle 5 justai-excepties + ValueError/RuntimeError, max_score-sommen) |
| Import-smoke | 5/5 ok |
| Entrypoint-smoke | arg-parsing, `print_report`, `print_results`, `generate_standalone_html` alle ok |

**Bewijs dat 5.2 een echte bug was**, gemeten tegen de vorige commit:
```
PRE-FIX:  ConnectionException ESCAPED run_prompt -> kaboom
POST-FIX: run_prompt returns ('E', None, None)
```

Netto over beide passes: `run.py`, `output.py`, `storage.py` samen **-43 regels** (SAFE) plus
**+20 regels** (LIKELY: 5.2 en 5.3 voegen bewust code toe, 2.1/2.2/3.1 halen weg).

## Nog te doen

1. **5.4** — `Storage.read` geeft `'0'` voor elke multi-answer prompt met wisselende scores,
   dus `print_results` toont 0 waar modellen 7, 9 of 5 van de 12 verschillen vonden. Bovenaan
   omdat het je huidige output onjuist maakt. Jouw beslissing omdat "het resultaat van
   meerdere passes" gedefinieerd moet worden (gemiddelde, som of laatste) en die definitie
   ook bepaalt wat er in de tabel hoort te staan.

Geen RISKY-findings in deze run.
