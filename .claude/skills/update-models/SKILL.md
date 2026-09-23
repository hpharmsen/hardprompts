---
name: update-models
description: Zoek nieuwe modellen van de labs die al in data/models.yaml staan, voeg ze toe, ruim vervangen modellen op, en draai de benchmark 3x. Gebruik bij vragen als "zijn er nieuwe modellen", "update de modellen", of "/update-models".
user_invocable: true
---

# Update models

Houdt `data/models.yaml` bij: nieuwe modellen erbij, achterhaalde modellen eruit, en meteen
benchmarken. Draait volledig automatisch, zonder tussentijds akkoord.

## Uitgangspunten

- **Alleen labs die er al in staan.** De labs volgen uit `LAB_PREFIXES` in `modelspecs.py`:
  OpenAI, Anthropic, Google, DeepSeek, Perplexity, xAI, Moonshot, MiniMax. Geen nieuwe
  providers toevoegen, dat vraagt ook een `justai` aanpassing.
- **Vergelijkbaar met wat er staat.** Tekst/vision chatmodellen in dezelfde reeksen, inclusief
  mini/lite/flash/nano varianten. Niet: `-batch` varianten, image-generatie, embeddings,
  en modellen die niet vrij op de API zitten (zoals Claude Mythos, dat vetted access vereist).
- **Nooit regels weggooien.** Opruimen is uitcommentariëren met een reden erachter, in de stijl
  van de bestaande `# - gpt-5.2-pro VEEL TE DUUR` regel. `data/results.jsonl` blijft altijd ongemoeid,
  daar zit de historie in.
- **`model@effort` regels zijn geen modellen.** Een entry als `claude-fable-5@low` is dezelfde
  model-id op een andere redeneerdiepte. Strip het `@level` deel voordat je vergelijkt, net als
  `split_effort()` in `modelspecs.py` doet, en tel ze niet mee als bestaande of nieuwe modellen.

## Stap 1: wat staat er nu

Lees `data/models.yaml` en `data/models.jsonl`. De jsonl geeft per model de prijs en het lab,
dat is de vergelijkingsbasis voor stap 4.

## Stap 2: zoek nieuwe modellen

Twee bronnen, en ze hebben verschillende rollen:

- **WebSearch per lab** om releases te vinden. Zoek per lab op recente aankondigingen.
- **De OpenRouter catalogus is de waarheid** over of iets echt bestaat en callable is:

```bash
curl -s https://openrouter.ai/api/v1/models | python3 -c "
import json,sys,datetime
d=json.load(sys.stdin)['data']
for m in sorted(d, key=lambda m: -m.get('created',0))[:60]:
    print(datetime.datetime.utcfromtimestamp(m.get('created',0)).date(), m['id'])
"
```

Sorteren op `created` laat direct zien wat nieuw is. Vergelijk met wat al in `models.yaml` staat.

**Voeg nooit een model toe dat je niet hebt kunnen verifiëren.** Als een blog een release claimt
maar OpenRouter en de docs van het lab kennen het model niet, dan is het niet uit. Pagina's met
titels als "X: Release Date and What to Expect" zijn speculatie, geen release. Meld zoiets als
"aangekondigd, nog niet beschikbaar" en ga door.

## Stap 3: bepaal de exacte API-id

De id die het lab in zijn eigen docs gebruikt wint van de OpenRouter-id en van wat een
nieuwsartikel schrijft. Twee valkuilen die eerder zijn misgegaan:

- **De marketingnaam is niet de id.** "OpenAI Astra" heet `gpt-6-astra`, "Claude 5.1" bestaat niet
  en is `claude-fable-5-1`. Zoek de id op bij het lab zelf voordat je hem toevoegt.
- **Anthropic schrijft versiepunten als streepjes** (`claude-fable-5-1`, niet `claude-fable-5.1`).
  De andere labs gebruiken meestal wel punten (`gpt-5.6-terra`, `grok-4.6`, `kimi-k2.6`).

Controleer daarna dat `justai` het model kan routeren: de prefix moet voorkomen in
`ModelFactory.create` in `justai/models/modelfactory.py`. Matcht de prefix niet, dan geeft elke
job een `I` of `N` en heeft benchmarken geen zin.

## Stap 4: ruim vervangen modellen op

Een nieuw model vervangt een oud model als alle drie kloppen:

1. Zelfde lab en zelfde klasse (vlaggenschip vervangt vlaggenschip, lite vervangt lite).
2. Prijs is gelijk of lager, af te lezen uit `models.jsonl` na stap 6.
3. Publieke benchmarks en de aankondiging van het lab positioneren het als opvolger.

Commentarieer het oude model dan uit met de reden erachter:

```yaml
  # - grok-4.5   vervangen door grok-4.6, zelfde prijs
```

**Doe dit nooit op basis van een slechte benchmarkrij.** Een rij vol `E`, `T`, `R`, `B`, `I` of `G`
zegt niets over de kwaliteit van het model, dat zijn infrastructuurfouten: geen credits,
rate limit, timeout. Alleen `X` en breuken zijn echte foute antwoorden. Bij twijfel: laten staan
en melden.

Twee prijsklassen naast elkaar zijn geen vervanging. `gpt-5.6-luna` en `gpt-5.6-terra` blijven
allebei staan, ook al is terra beter, want terra is tien keer zo duur.

Een model en zijn eigen effort-varianten zijn nooit elkaars vervanger, die horen bij elkaar.
Commentarieer je een basismodel uit, haal dan ook zijn `@level` regels weg, anders draaien die
door zonder referentiepunt.

## Stap 5: voeg toe aan models.yaml

Zet nieuwe modellen bij hun eigen lab in de lijst, in versievolgorde. Zet een comment achter
modellen die opvallen, in de stijl die er al staat:

```yaml
  - gpt-6-astra          # $10/$50 per M tokens, dus duur
  - deepseek-v4-flash    # V4 is text-only, dus slaat de visuele prompts over
```

Voeg zelf geen `@level` varianten toe. Die staan in een apart blok onderaan en zijn een bewuste
keuze per model, geen automatisme. Vervangt een nieuw model een basismodel dat wel varianten
had, meld dan dat die varianten meeverhuisd kunnen worden en welke levels het lab native
ondersteunt, maar laat de keuze aan HP.

## Stap 6: haal de specs op

```bash
.venv/bin/python modelspecs.py
```

Elke regel moet een prijs tonen. Staat er `NOT FOUND`, dan matcht de key niet op OpenRouter:
controleer de spelling, of voeg een `SPEC_OVERRIDES` entry toe als OpenRouter het model niet
heeft (zoals bij `MiniMax-M2.7-highspeed`). Controleer daarna in `data/models.jsonl` dat de
`name` van elk nieuw model klopt en niet die van een voorganger is.

Wijkt de prijs op OpenRouter af van wat je bij het lab zelf leest, bijvoorbeeld door een tijdelijke
korting, neem dan de listprijs van het lab in `SPEC_OVERRIDES` op met een comment erbij.

## Stap 7: benchmark

```bash
.venv/bin/python main.py -n=3 -c
```

`uv` en `python` staan niet op het PATH in een niet-interactieve shell, gebruik `.venv/bin/python`.

De cache in `data/results.jsonl` zorgt dat alleen ontbrekende passes draaien, dus dit is
goedkoper dan het lijkt: modellen die al op 3 passes staan worden overgeslagen. Tel vooraf
hoeveel jobs het worden:

```bash
.venv/bin/python -c "
import tomllib, yaml
from run import get_jobs
P=tomllib.load(open('data/prompts.toml','rb')); M=yaml.safe_load(open('data/models.yaml'))['models']
tc={k:v for k,v in P.items() if not v.get('image')}
print(len(get_jobs(M, tc, 3, True)), 'jobs')
"
```

Draai in de achtergrond, want dit duurt lang. De voortgang staat live in `jobs.log`, niet in de
stdout van het commando zelf (die is gebufferd).

Losse cellen die op `B` of `T` eindigen zijn meestal een gevolg van de 12 gelijktijdige jobs bij
`-c`. Draai die daarna nog een keer zonder `-c`, bijvoorbeeld
`.venv/bin/python main.py claude-fable-5-1 BIRMEES -n=3`.

## Stap 8: rapporteer

Vertel kort:

- Welke modellen zijn toegevoegd, met id, prijs en contextvenster.
- Welke zijn uitgecommentarieerd en waarom.
- Wat er aangekondigd is maar nog niet beschikbaar, zodat het bij de volgende run terugkomt.
- De scores van de nieuwe modellen, en apart daarvan de rijen die op infrastructuurfouten
  stukliepen, met wat eraan te doen is (credits bijladen, rate limit).

Committen doe je niet, dat doet HP zelf.
