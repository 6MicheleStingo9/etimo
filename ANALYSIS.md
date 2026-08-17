# Analisi di solidità

Diagnosi indipendente di `etimo`, condotta l'11 agosto 2026 su due assi: la
**tenuta linguistica** delle catene che produce e la **solidità del software**
che le costruisce.

> **Nota, 11 agosto 2026 — le correzioni sono state applicate.**
> Questo documento descrive il codice **com'era**, e resta come registro di ciò
> che è stato trovato e di come è stato misurato. Gli interventi del §7 sono poi
> stati eseguiti; l'esito è riassunto in [§8](#8-dopo-le-correzioni), rimisurato
> sullo stesso campione.
>
> **Nota, 12 agosto 2026 — secondo e terzo giro.**
> Un riesame condotto in coppia con una seconda sessione ha trovato una classe di
> difetto che il primo giro non aveva visto: i template scritti nella **riga di
> definizione** anziché nella sezione «Etymology». L'esito è in
> [§9](#9-secondo-giro-i-template-in-riga-di-definizione), insieme a una nota di
> metodo sulle sette volte in cui le misure di questo documento hanno dovuto
> essere corrette. Il [§10](#10-terzo-giro-lidioma-del-trattino-e-il-terminale-mancante)
> chiude le questioni che il secondo aveva lasciato aperte, e ne ribalta una: la
> classe archiviata come trascurabile era tre volte più grande di quella promossa
> a intervento principale.

**Ambiente di misura.** Python 3.11.15, `mwparserfromhell` 0.7.2,
`sys.getrecursionlimit()` = 1000, Linux 6.8. Sorgente: en.wiktionary.org
interrogata l'11 agosto 2026; 360 richieste per il corpus diagnostico, ~280 per
il campionamento, User-Agent identificante e intervallo di 0,5 s come previsto
dal codice. Le prove offline girano su `DictSource` e su un `urlopen` iniettato:
non dipendono dallo stato di Wiktionary e sono ripetibili.

---

## 1. In una pagina

`etimo` è un progetto scritto con cura non comune. L'architettura a strati è
netta — `wikitext` non fa I/O, `walker` non conosce la rete, `render` restituisce
stringhe e non stampa — e regge su un `Protocol` con tre implementazioni
intercambiabili che rende testabile tutto il resto senza un solo mock. Gli 80
test passano in mezzo secondo senza toccare la rete. I docstring argomentano le
decisioni invece di descrivere il codice. Sono qualità che non si improvvisano.

Il progetto si è però dato un criterio esplicito, scritto nel sorgente:

> *A chain can stop because the language has nothing more to say — a
> reconstructed root, a declared uncertain origin — or because the tool could not
> go on. These are different things and must stay distinct in the result,
> otherwise a technical limit disguises itself as a linguistic fact.*
> — [`walker.py:10-14`](src/etimo/walker.py#L10-L14)

**È questo criterio che il programma non rispetta.** Non per un difetto isolato,
ma perché tre meccanismi indipendenti convergono nello stesso esito: quando lo
strumento non capisce, tace dichiarando che è la lingua a tacere.

Su un corpus diagnostico di **113 voci** scelte per coprire i fenomeni della
storia linguistica italiana, e su un campione casuale di **400 lemmi** estratti
dall'intero elenco delle voci italiane:

| misura | valore |
| --- | --- |
| foglie dell'albero che dichiarano un **fatto linguistico** (`√` `⊗` `·`) | **124 su 161 — 77%** |
| voci del corpus che non producono **nessun passo** | **39 su 113 — 34,5%** |
| di queste, imputabili allo **strumento** (la fonte ha il dato, etimo non lo legge) | **19** |
| di queste, imputabili alla **fonte** (il dato non esiste), correttamente dichiarate | **13** |
| di queste, corrette (la fonte dichiara davvero l'origine incerta) | **4** |
| di queste, al confine: la fonte usa la prosa dove servirebbe un template | **3** |
| «fatti linguistici» dichiarati che sono in realtà artefatti dello strumento | **almeno il 15%** |
| sezioni «Etymology» del campione che etimo non riesce a leggere | **32,9%** (IC 95% 27,8–38,4) |
| di quelle, quante sarebbero leggibili **solo estendendo la whitelist** | **41,2%** (IC 95% 32,0–51,2) |

Tre esempi bastano a dare la misura del problema, e sono tutti riproducibili:

- `etimo computer` risponde `· data exhausted`, che il programma classifica come
  fatto sulla lingua. La voce di Wiktionary dice `{{ubor|it|en|computer}}`: il
  dato c'è, il template non è in whitelist. Vale per **812** voci italiane.
- `etimo bravo` risponde `*bravus (la-vul) → √ reconstructed root`. La fonte
  dichiara `{{unc}}` — origine incerta — e presenta `*bravus` come una *proposta*
  fra altre, seguita da «Less likely from…». L'incertezza dichiarata sparisce e
  una congettura diventa una radice ricostruita.
- `etimo dado` risponde che il latino `datum` viene dall'arabo `أَعْدَاد`,
  annotando «step reported by the entry «dado»». La fonte dice «*either* from
  `datum`, *or* from `aʿdād`»: due alternative rivali diventano due anelli
  consecutivi, e un anacronismo riceve una citazione di provenienza.

Sul versante software la base è solida ma il perimetro è scoperto proprio dove
serve: `cli.py` ha **copertura di test 0%**, `wiktionary.py` — che contiene
retry, backoff e gestione degli errori HTTP — ha **10% di copertura dei rami**, e
in quel modulo cinque risposte anomale realistiche escono come traceback grezzo.

**Il giudizio complessivo**: il progetto ha ragione nell'impianto e sbaglia
nell'applicazione. Le correzioni che sanerebbero la maggior parte dei casi sono
concentrate — una dozzina di nomi in due dizionari, tre voci in una tabella, una
condizione in `_data_end` — e non richiedono di ripensare l'architettura. Il
difetto che invece tocca il modello, non l'implementazione, è il trattamento
delle alternative in concorrenza (§3.3).

---

## 2. Come è stato verificato

**Principio di non contaminazione.** Tutto l'audit vive fuori dal repository, in
un venv usa-e-getta con `PYTHONPATH` sul sorgente: nessun pacchetto installato,
nessun `.pth`, nessun `__pycache__`, nessuna modifica a `pyproject.toml`. Il
confronto dell'impronta dei file prima e dopo è identico. La cache dell'utente
(`~/.cache/etimo/pages.sqlite`) non è stata letta né modificata: le prove di rete
usano `XDG_CACHE_HOME` in una directory temporanea.

**Offline** — parser e walker su wikitext fisso; `urllib.request.urlopen`
sostituito da una risposta fittizia per sondare il comportamento in errore; DB
SQLite di prova; variabili d'ambiente per encoding e colori; `pytest-cov` per la
copertura reale.

**Con rete** — un corpus diagnostico di 113 voci scelte per stressare fenomeni
precisi (voci ereditarie, coppie dotto/popolare, prestiti a mediazione multipla,
germanismi, grecismi, composti, onomatopee, etimi incerti, omografi, sostrato,
sigle ed eponimi, anglicismi, input patologici, voci a copertura scarsa, più
cinque voci latine); il conteggio delle transclusioni via `insource:` con
espressione regolare; un campione casuale da `Category:Italian lemmas`.

**Che cosa questa analisi non copre.** Non valuta l'esattezza etimologica di
Wiktionary rispetto al DELI o al Nocentini — misura lo scarto fra ciò che la
fonte dice e ciò che etimo riporta, che è una domanda diversa e verificabile
meccanicamente. Non copre lingue di partenza diverse dall'italiano e dal latino.
Non misura il comportamento sotto carico né in concorrenza fra processi.

**Una precisazione di metodo.** La prima aggregazione dei risultati classificava
`girasole`, `asciugamano` e `saliscendi` come «nessun template riconoscibile»:
era un difetto del filtro di analisi, che scartava come rumore i template
`it-*` — fra cui `{{it-verb-obj}}`, che è etimologico. I numeri di questo
documento vengono dalla riclassificazione corretta.

---

## 3. Solidità linguistica

### 3.1 Che cosa etimo legge davvero della fonte

Il principio dichiarato in [`wikitext.py:5-8`](src/etimo/wikitext.py#L5-L8) —
whitelist e mai blacklist — è giusto: enumerare i template da scartare, su un
wiki che ne aggiunge di continuo, prima o poi promuoverebbe ad antenato qualcosa
che non lo è. Il problema non è il principio ma **l'ampiezza della lista**, che
non copre i template più usati proprio nelle voci italiane.

Conteggi misurati su en.wiktionary l'11 agosto 2026 con ricerca a espressione
regolare (`insource:/…/`), voci del namespace principale:

| template non riconosciuto | che cosa esprime | voci italiane |
| --- | --- | ---: |
| `{{rfe}}` | *la fonte dichiara di non avere ancora l'etimologia* | **7 760** |
| `{{uder}}` | derivazione senza datazione | **2 738** |
| `{{alt form}}` | variante formale | **2 398** |
| `{{it-verb-obj}}` | composto verbo + oggetto (`girasole`) | **1 259** |
| `{{surf}}` | analisi di superficie | **1 089** |
| `{{ubor}}` | prestito non adattato (`computer`, `film`) | **812** |
| `{{it-deverbal}}` | deverbale (`peso`, `abbiocco`) | **537** |
| `{{apocopic form of}}` | apocope (`far`, `son`) | **524** |
| `{{abbreviation of}}`, `{{ellipsis of}}`, `{{initialism of}}` | abbreviazioni e sigle | 301 |
| `{{pseudo-loan}}`, `{{named-after}}`, `{{dbt}}`, `{{univ}}` | pseudoprestiti, eponimi, alias | 253 |
| `{{contraction of}}`, `{{clipping of}}`, `{{acronym of}}`, altri | | 118 |
| | **totale** | **≈ 17 800** |

Su **129 636** lemmi italiani, sono circa il **14%**. Il confronto interno è
istruttivo: `{{clipping}}` e `{{short for}}` *sono* in whitelist, `{{clipping of}}`
— che è il nome canonico su en.wiktionary — no. L'esclusione non può quindi
essere una scelta di principio sul fenomeno: è un'omissione di nome. Lo stesso
vale per `lbor`/`slbor`/`obor`, presenti solo in forma abbreviata mentre
`der`/`inh`/`bor`/`cal` hanno entrambe le forme.

Un caso merita di essere isolato. **`{{rfe}}` è la marca con cui un redattore
segnala che l'etimologia manca**: è la dichiarazione esplicita di un limite della
fonte, cioè esattamente l'informazione che il progetto vuole distinguere. etimo
la ignora e produce `· data exhausted`, un fatto linguistico. La categoria
giusta esiste già nel modello — `ETYMOLOGY_MISSING`, `is_linguistic=False`, con
un messaggio della CLI che dice «*This is not a gap in the tool: the data is not
in the source*» — semplicemente non ci si arriva.

Da segnalare in senso opposto: il formato legacy `{{etyl}}`, che sembrava un
candidato ovvio, ha **19 occorrenze in tutto il sito** e zero nelle voci
italiane. Non è un difetto rilevante e non entra nel bilancio.

#### La copertura, misurata contro l'inventario di Wiktionary

La domanda «quanti template esistono e quanti ne legge Etimo» ha una risposta
esatta, perché Wiktionary li raccoglie in una propria categoria.
`Category:Etymology templates` e le sue sottocategorie (`Foreign derivation
templates`, `Morphology templates`, `Language-specific morphology templates`)
contengono **129 template canonici**; seguendo i redirect si arriva a **224 nomi
con cui possono essere invocati**. La whitelist di Etimo ne riconosce **45**.

| | |
| --- | ---: |
| nomi invocabili su en.wiktionary | 224 |
| nomi riconosciuti da Etimo | **45 — 20%** |
| template canonici mai riconosciuti sotto alcun nome | **101 su 129** |
| template riconosciuti solo sotto una parte dei loro nomi | 11 |

Quest'ultima riga è la più istruttiva, perché mostra che l'omissione non segue
alcun criterio:

| template | nomi che funzionano | nomi che non funzionano |
| --- | --- | --- |
| `confix` | `con` | **`confix`** |
| `clipping` | `clipping` | `clip` |
| `doublet` | `doublet` | `dbt` |
| `univerbation` | `univerbation` | `univ` |
| `learned borrowing` | `lbor` | `learned borrowing` |
| `semi-learned borrowing` | `slbor` | `semi-learned borrowing`, `slb` |
| `orthographic borrowing` | `obor` | `orthographic borrowing` |
| `back-formation` | `back-form`, `backformation` | `back-formation`, `bf`, `backform`, `b-f` |
| `prefix` | `prefix`, `pre` | `pref` |
| `noncognate` | `noncog`, `ncog` | `noncognate` |
| `onomatopoeic` | `onomatopoeic`, `onom` | `onomatopeic`, `onomatopoeia` |

Lo stesso fenomeno è letto o ignorato a seconda di quale sinonimo il redattore
della voce ha digitato. `{{con|it|a|b}}` funziona, `{{confix|it|a|b}}` no.

**Il 20% è però una misura per nome, non per uso.** Su un campione casuale di
**2 000 lemmi italiani** (1 324 con sezione «Etymology», 1 421 sezioni, 2 502
occorrenze di template nel corpo etimologico):

| classe di template | occorrenze | quota |
| --- | ---: | ---: |
| **riconosciuti da Etimo** | 2 103 | **84,1%** |
| non riconosciuti, ma che dichiarano un **terminale** (`rfe`, `named after`, `pseudo-loan`…) | 131 | 5,2% |
| non riconosciuti, ma che dichiarano un **anello** (`uder`, `confix`, `ubor`…) | 102 | 4,1% |
| note accessorie (`surf`, `lit`, `false cognate`…) — ignorarle è corretto | 79 | 3,2% |
| servizio e rendering (`etydate`, `desctree`, `nonlemma`…) — ignorarli è corretto | 47 | 1,9% |
| pertinenti ad altre lingue o fuori categoria | 40 | 1,6% |

**L'informazione etimologica realmente perduta è il 9,3%** delle occorrenze: 233
su 2 502. Il restante 6,7% di template non riconosciuti non è una perdita — sono
rimandi, categorizzazioni e note che *devono* essere ignorati.

E la perdita è concentratissima. Cinque nomi coprono 220 delle 233 occorrenze:

| template | occorrenze | voci | resa corretta |
| --- | ---: | ---: | --- |
| `rfe` | 126 | 125 | terminale `?` — *la fonte dichiara di non sapere* |
| `uder` | 42 | 38 | `DERIVED` |
| `confix` | 31 | 31 | `AFFIXATION` (l'alias `con` è già coperto) |
| `it-deverbal` | 11 | 11 | derivazione interna |
| `ubor` | 10 | 10 | `BORROWED` |
| *altri 13 nomi* | 13 | 13 | vari |

#### Quanto pesa, su un campione casuale

I conteggi qui sopra dicono quante voci contengono un template; non dicono quante
catene si spezzano. Per misurarlo è stato scaricato l'elenco completo delle
**129 636** voci di `Category:Italian lemmas` e campionato **400 lemmi** con
campionamento casuale a seme dichiarato (20260811). Per ciascuno si è isolata la
sezione italiana, poi le sezioni «Etymology», poi si è eseguito il parser di
etimo e lo si è confrontato con una variante che estende la whitelist.

| misura | k/n | stima | IC 95% |
| --- | ---: | ---: | :---: |
| voci prive di sezione «Etymology» — *limite della fonte* | 132/400 | 33,0% | 28,6–37,8 |
| sezioni «Etymology» che non producono né passi né incertezza | 97/295 | **32,9%** | 27,8–38,4 |
| — di queste, **leggibili estendendo la whitelist** → *difetto dello strumento* | 40/97 | **41,2%** | 32,0–51,2 |
| — di queste, prive di informazione strutturata → *limite della fonte* | 57/97 | 58,8% | 48,8–68,0 |
| sezioni il cui corpo ingloba le sottosezioni (`====Noun====`, `====Descendants====`) | 49/295 | 16,6% | 12,8–21,3 |
| falsa incertezza in prosa che sopprime `{{ety}}` | 0/295 | 0,0% | 0,0–1,3 |

Due letture. La prima: **circa un terzo delle sezioni etimologiche italiane non
produce nulla**, e di queste **due su cinque** conterrebbero un antenato leggibile
se la whitelist coprisse i nomi giusti. Tradotto sull'intero elenco, sono
dell'ordine di **quattromila voci** che tacciono per un difetto rimediabile
aggiungendo righe a un dizionario.

Sul campione più ampio di 2 000 lemmi l'effetto delle aggiunte è quantificabile
con precisione:

| sezioni «Etymology» da cui Etimo ricava qualcosa | n/1 421 | quota | IC 95% |
| --- | ---: | ---: | :---: |
| oggi | 980 | **69,0%** | 66,5–71,3 |
| aggiungendo i **cinque** template più frequenti | 1 182 | **83,2%** | 81,1–85,0 |
| aggiungendo tutti e **diciotto** | 1 191 | 83,8% | 81,8–85,6 |
| residuo non recuperabile con i template: prosa o rimandi con `{{m}}` | 230 | 16,2% | 14,4–18,2 |

Cinque righe in due dizionari portano la lettura dal 69% all'83% delle sezioni.
Le altre tredici aggiungono mezzo punto: è la coda lunga, e va coperta per
completezza, non per resa.

La seconda riguarda l'onestà del bilancio: **la maggioranza delle sezioni vuote —
il 58,8% — è un limite reale della fonte**, e lì etimo non ha colpe. Il difetto è
grave non perché sia la causa prevalente, ma perché le due situazioni escono
dall'output **indistinguibili**, entrambe come `· data exhausted`.

Il campione ha anche corretto una previsione: la falsa incertezza da prosa
(§3.3), riproducibile in laboratorio, ha incidenza **nulla** sulle voci reali. E
ha portato alla luce altri template etimologici non censiti — `{{confix}}`,
`{{apheretic form}}`, `{{apocopic form}}`, `{{ellipsis}}`, `{{initialism}}`,
`{{piecewise doublet}}` — cioè le varianti *senza* il suffisso « of », che la
lista del §3.1 non copriva: il conto reale dei nomi mancanti è più alto di quello
là riportato.

### 3.2 Che cosa etimo dice di sapere e non sa

È il cuore dell'analisi. La tabella dei terminali del corpus, con la colonna che
il progetto stesso rende decisiva:

| terminale | n | % foglie | dichiarato | veridico? |
| --- | ---: | ---: | --- | --- |
| `√ reconstructed root` | 66 | 41,0% | **fatto linguistico** | **no, in una parte dei casi** (§3.2.1) |
| `· data exhausted` | 51 | 31,7% | **fatto linguistico** | **no, in 19 casi su 51** |
| `? no etymology recorded` | 16 | 9,9% | limite | sì |
| `? no Wiktionary entry` | 10 | 6,2% | limite | sì |
| `? language not covered` | 9 | 5,6% | limite | sì, ma spesso per colpa dello strumento (§3.2.2) |
| `⊗ uncertain origin` | 7 | 4,3% | **fatto linguistico** | sì nei 4 casi verificati |
| `↺ circular reference` | 2 | 1,2% | limite | 1 vero, 1 falso |

Il 77% delle foglie afferma qualcosa sulla lingua. Almeno il 15% di quelle
affermazioni è un artefatto.

#### 3.2.1 Il falso «√ radice ricostruita»

[`walker.py:244-252`](src/etimo/walker.py#L244-L252) riclassifica in
`RECONSTRUCTED_ROOT` qualunque terminale, se la forma è ricostruita. Il commento
motiva **un** caso — una proto-forma di cui non si sa altro — ma il metodo è
chiamato in **cinque** punti, e tre di essi sono assenze: voce mancante, lingua
non coperta, etimologia assente. «Non ho trovato la pagina» esce come «qui la
ricostruzione comparativa si ferma».

Verificato su dati reali:

```text
$ etimo prete
prete (it)
└─ inherited from Old Italian
   └─ preite (roa-oit)
      └─ inherited from Vulgar Latin
         └─ *previter (la-vul)
            └─ √ reconstructed root
```

La pagina `Reconstruction:Vulgar Latin/previter` **non esiste** (verificato:
memorizzata in cache con `found=0`). La catena vera prosegue per `presbyter` fino
al greco `πρεσβύτερος`: due anelli persi, e la perdita è dichiarata come punto
d'arrivo della ricostruzione comparativa.

Il difetto si aggrava quando si combina con la tabella delle lingue: per un
codice proto non presente in `_LANGUAGES`, `page_title()` costruisce
`Reconstruction:<codice grezzo>/lemma` — un titolo che non esisterà mai — e
`_data_end` converte il 404 risultante in `√`. L'errore è quindi **sistematico**
per ogni famiglia linguistica fuori tabella.

```text
$ etimo betulla
   └─ betulla (la)
      └─ borrowed from an unregistered language (cel-gau)
         └─ *bitu (cel-gau)
            └─ √ reconstructed root       ← Reconstruction:Celtic/bitu non esiste
```

#### 3.2.2 I codici lingua, e una divergenza interna

`languages.py` contiene 151 lingue. Tre casi misurati sono frequenti e producono
esiti diversi ma tutti sbagliati:

| codice | occorrenze | che cosa accade |
| --- | ---: | --- |
| `cel-gau` (gallico) | **1 323** | non è in tabella; `wiktionary_name()` ripiega sulla base `cel` e cerca la sezione `==Celtic==`, che non esiste — la sezione reale è `==Gaulish==` |
| `la-eme` (latino altomedievale) | **766** | è in tabella ma **manca dal fallback di sezione**: `bianco` si ferma al primo passo con `? language not covered`, perdendo la tappa francone che la voce annuncia |
| `VL.` | **111** | sigla malformata usata nelle voci; nessuna gestione |

Qui c'è un difetto interno che vale la pena isolare. `language_name()` è onesta e
restituisce «unregistered language (cel-gau)»; `wiktionary_name()`, che è quella
usata per **cercare la sezione e costruire l'URL**, restituisce invece
«Celtic» — un nome plausibile ma falso. Le due funzioni divergono proprio dove
il docstring del modulo promette che «una sola tabella» impedisce ai tre usi di
divergere. Cercare `==Celtic==` è peggio che fallire subito: è cercare la lingua
sbagliata.

Non gestiti neppure i parametri con **più codici**: `{{der+|it|roa-oca,oc-pro|escac}}`
produce una forma la cui «lingua» è la stringa `roa-oca,oc-pro`, e l'utente legge
`derived from an unregistered language (roa-oca,oc-pro)`.

#### 3.2.3 Il falso «· dati esauriti»

Diciannove voci del corpus su 113 escono con `·` — «l'entrata non registra
altro» — mentre l'entrata registra eccome:

| voce | terminale | che cosa dice davvero la fonte |
| --- | --- | --- |
| `computer`, `film`, `golf` | `· data exhausted` | `{{ubor}}` (prestito non adattato) |
| `limone`, `torso`, `ministero` | `· data exhausted` | `{{uder}}` (derivazione non datata) |
| `girasole`, `asciugamano` | `· data exhausted` | `{{it-verb-obj}}` |
| `saliscendi` | `· data exhausted` | `{{it-verb-verb}}` |
| `invece` | `· data exhausted` | `{{univ}}` (alias di `univerbation`) |
| `fuggifuggi` | `· data exhausted` | `{{reduplication}}` |
| `box` | `· data exhausted` | `{{pseudo-loan}}` |
| `paparazzo` | `· data exhausted` | `{{named-after}}` + `{{surf}}` |
| `moto` | `· data exhausted` | «Shortened form of…» con `{{m}}` |
| `tintinnare`, `scugnizzo` | `· data exhausted` | `{{rfe}}` — la fonte *dichiara* di non sapere |
| `muta`, `abbiocco` | `· data exhausted` | `{{it-deverbal}}` |

Le ultime tre righe meritano una distinzione. `veglia`, `moto` e `sfogliatella`
sono casi in cui la fonte esprime l'etimologia in prosa usando `{{m}}`, un
template di menzione: qui la whitelist di etimo applica correttamente il proprio
principio, ed è la fonte a codificare male. Vanno contati a parte — sono il
confine legittimo dell'approccio, non un errore di lettura.

#### 3.2.4 Il falso «↺ riferimento circolare»

Il set `visited` è unico per l'intera visita e non viene mai svuotato in
backtracking ([`walker.py:337-344`](src/etimo/walker.py#L337-L344)): non registra
«antenato nel percorso corrente» ma «già visto ovunque». Due rami di un composto
che riconvergono sullo stesso antenato — situazione ordinaria in etimologia —
producono sul secondo `↺ circular reference`, che il modello classifica come
**limite del tool**. Un fatto linguistico presentato come guasto tecnico: la
simmetria esatta dell'errore che il progetto vuole evitare.

Sul corpus, `dopodomani` lo esibisce: i due rami si ritrovano sul latino `dē`. La
verifica formale — la chiave del nodo non compare fra i propri antenati —
distingue meccanicamente i due casi.

Va detto il rovescio: **`auto` produce un ciclo vero** (`auto → automobile →
auto`, perché Wiktionary è realmente circolare qui) e viene gestito
correttamente. Il difetto non è la rilevazione dei cicli, che funziona, ma il non
distinguere il ciclo dalla confluenza.

#### 3.2.5 Le ipotesi spariscono se la parola cercata è quella incerta

Un'asimmetria fra due rami del codice produce un risultato che cambia a seconda
di *come* si arriva alla stessa voce. Quando un nodo interno si chiude con un
terminale, `_expand` gli assegna anche le ipotesi lette dalla fonte
([`walker.py:347-352`](src/etimo/walker.py#L347-L352)); quando è il **nodo di
partenza** a chiudersi, `reconstruct` assegna terminale e nota ma **non** le
ipotesi ([`walker.py:145-149`](src/etimo/walker.py#L145-L149)).

Le stesse due congetture sulla stessa voce compaiono o spariscono a seconda della
domanda:

```text
$ etimo fuoco                          $ etimo focus --language la
fuoco (it)                             focus (la)
└─ inherited from Latin                └─ ⊗ uncertain origin
   └─ focus (la) «hearth»
      └─ ⊗ uncertain origin            0 steps · terminal: uncertain origin
         perhaps *bʰeh₂- «to shine» …
         perhaps *dʰegʷʰ- «to burn» …
```

Il secondo comando è uno degli esempi d'uso del README. Chi interroga
direttamente una parola di etimo incerto — cioè il caso in cui le congetture sono
l'informazione più interessante che la voce contiene — non le vede.

### 3.3 Che cosa etimo attribuisce alla fonte e la fonte non dice

Più grave del tacere è l'affermare. Tre meccanismi fabbricano anelli che la fonte
non contiene.

**Il termine citato come confronto diventa antenato.** `_parse_body` riconosce
qualunque template di relazione nella prosa, senza guardare la funzione
discorsiva della frase. «*Compare {{der|it|de|Bank}}*» è indistinguibile da
«*from {{der|it|de|Bank}}*».

**La catena riportata attraversa i confini di lingua.** `CarriedChain` è un'idea
giusta — quando un antenato non ha voce propria, la voce di partenza spesso
descrive il resto del percorso — ma non verifica che il passo successivo sia
coerente con il nodo su cui viene innestato. Wiktionary àncora **ogni** template
alla lingua della voce, non a quella del link precedente: è il principio n. 2 che
lo stesso modulo `wikitext` dichiara. Innestare quel passo sotto il nodo
successivo produce un'asserzione che nessuno ha fatto:

```text
$ etimo dado
dado (it)
└─ derived from Latin
   └─ datum (la) «thrown, given»
      └─ derived from Arabic
         └─ أَعْدَاد (ar) «numbers»
            · step reported by the entry «dado»
```

Il latino `datum` non viene dall'arabo. La voce dice «*Perhaps from `*dadu`,
itself **either** from `datum`, **or** from `aʿdād`*»: due ipotesi alternative,
che il programma dispone in fila come se fossero una discendenza, e certifica con
un'attribuzione.

**Le alternative in concorrenza diventano una catena.** È il difetto di modello,
non di implementazione. L'assunzione dichiarata — *l'ordine testuale è l'ordine
della catena* — è corretta per le etimologie lineari («from X, from Y») e falsa
per quelle che elencano proposte rivali. Le formule sono ricorrenti: «Probably…
Less likely…», «either… or…», «Perhaps…, or…», «Ultimately from X, via Y» (dove
l'ordine è addirittura invertito).

Il caso `bravo` mostra il danno completo:

```text
wikitext:  {{unc|it}} Probably from {{der|it|la|*bravus}}, from a fusion of
           prāvus and barbarus. Less likely from {{der|it|pro|brau}}, from
           {{der|it|cel-gau|*bragos}}.

etimo:     bravo (it)
           └─ inherited from Vulgar Latin
              └─ *bravus (la-vul)
                 └─ √ reconstructed root
```

La fonte dichiara `{{unc}}` — origine incerta — e propone due ricostruzioni in
concorrenza. L'output non contiene traccia dell'incertezza e presenta la prima
proposta come radice ricostruita, cioè come uno dei terminali che il progetto ha
scelto di riconoscere come fatti.

La causa è una sola riga: `_read` impone `UNCERTAIN_ORIGIN` solo se
`analysis.uncertain **and not** analysis.steps`
([`walker.py:237`](src/etimo/walker.py#L237)). Se la voce dichiara l'incertezza
*e* nomina delle proposte, l'incertezza perde. Vale anche per `mafia`
(«*{{unc}}. Maybe from…*») e `pizza`.

Il difetto ha una faccia opposta e simmetrica. Il flag `uncertain` è un booleano
che non sa **a che cosa** l'incertezza si riferisca:

- quando è espressa in prosa e riguarda l'**antenato** («*Borrowed from Arabic, a
  word of uncertain origin*»), il flag scatta sulla voce corrente e produce un
  falso `⊗`; peggio, la guardia di [`wikitext.py:544`](src/etimo/wikitext.py#L544)
  usa lo stesso flag per decidere se leggere `{{ety}}`/`{{etymon}}`, quindi una
  falsa incertezza **spegne anche il formato strutturato** — che per il latino è
  l'unica fonte in circa una voce su cinque, come il README stesso documenta;
- quando è dichiarata con `{{unc}}` e accompagnata da proposte, viene scartata.

Infine la regex che riconosce l'incertezza in prosa copre le formule con
«origin/etymology/derivation» ma non le più brevi: `Uncertain.`,
`Uncertain, possibly from…`, `Disputed.`, `Etymology unclear.` non scattano. È
per questo che `mucca` esce affermando una derivazione dallo svizzero-tedesco che
la fonte presenta come possibilità.

**I discendenti presentati come ipotesi di antenati.** `_parse_hypotheses`
raccoglie qualunque riga di lista contenente un template di relazione, e
l'etichetta nel rendering è `perhaps X` — cioè «forse questo è l'antenato».
Righe come `* Descendants: {{der|it|scn|focu}}` finiscono lì dentro. La causa
profonda è strutturale: `etymology_sections` chiude una sezione solo su un
heading di rango pari o superiore, quindi il corpo di `===Etymology 1===`
**ingloba `====Noun====`, `====Descendants====` e `====Derived terms====`**. Il
parser lavora quindi su un testo che contiene il resto della voce.

```text
corpo restituito per «Etymology 1»:
  'From {{inh|it|la|focus}}.\n\n====Noun====\n{{it-noun|m}}\n\n
   ====Descendants====\n* {{der|scn|it|focu}}\n\n====Derived terms====…'
hypotheses: [('focu', 'it', None)]      ← discendente siciliano, e con lingua sbagliata
```

Il codice lingua stampato è per giunta errato: `_form_from_relation` legge il
parametro 2, che in `{{der|scn|it|focu}}` è la lingua *di partenza*.

### 3.4 Il modello concettuale

Al di là dei singoli difetti, tre scelte meritano una discussione.

**«Radice ricostruita» applicata a ciò che radice non è.** Ogni proto-forma senza
continuazione riceve `√ reconstructed root`. Ma `*patēr` proto-italico è una
*parola* ricostruita e `*-tḗr` è un *suffisso*: nell'esempio di punta del README,
`*-tḗr` compare etichettato «reconstructed root». In indoeuropeistica la
distinzione fra radice, tema e affisso è portante, e l'etichetta unica la
cancella. Il modello avrebbe bisogno di separare «forma ricostruita» da «radice».

**Nessun controllo di plausibilità cronologica.** Nulla impedisce che il tedesco
moderno risulti antenato del longobardo, o l'arabo del latino. La tabella
`_LANGUAGES` conosce già le fasi storiche (`itc-pro` → `itc-ola` → `la` →
`la-lat` → `la-med` → `it`): un ordinamento parziale, anche grossolano,
intercetterebbe buona parte degli anelli fabbricati di §3.3 a costo quasi nullo,
e sarebbe un controllo *linguistico*, non euristico.

**`{{der}}` equiparato a `{{inh}}` e `{{bor}}`.** Su Wiktionary `der` significa
«in ultima analisi da», ed è la marca usata proprio quando gli stadi intermedi
sono taciuti. Trattarlo come un anello percorribile produce catene che *saltano*
stadi presentandoli come contigui. La scelta è difendibile — senza `der` molte
catene si interromperebbero — ma andrebbe dichiarata nel rendering, che oggi
scrive «derived from X» allo stesso rango di un'eredità.

**Un'ultima osservazione, a favore.** La distinzione fra trafila dotta e popolare
— il banco di prova classico della linguistica italiana — **funziona**:

```text
$ etimo vizio          $ etimo vezzo
vizio (it)             vezzo (it)
└─ borrowed from Latin └─ inherited from Latin
   └─ vitium (la)         └─ vitium (la)
```

Stessa forma latina, due modi di passaggio distinti, e il doppione segnalato in
nota. Lo stesso vale per `causa`/`cosa` e `plebe`/`pieve`. È merito della scelta
di modellare la relazione come tipo e non come attributo
([`models.py:1-7`](src/etimo/models.py#L1-L7)), ed è la prova che l'impianto
concettuale regge dove i dati arrivano.

### 3.5 Che cosa è davvero limite della fonte

Tredici voci del corpus su 113 (11,5%) si fermano perché il dato non esiste, e in
tutti questi casi **etimo si comporta correttamente**: distingue la pagina
assente (`un'ora`, `sgrunfiare`) dalla pagina che non copre la lingua (`Fuoco`,
maiuscolo, che su en.wiktionary è un'altra voce) dalla voce priva di sezione
etimologica (`vigilia`, `PC`, `sciampo`, `cavitazione`, `case`), e il messaggio
della CLI suggerisce il rimedio giusto per ciascun caso.

Va anche smentita un'aspettativa: la copertura di Wiktionary sul lessico
regionale **non** è uniformemente povera. `'nduja` produce tre anelli corretti
fino al latino attraverso il francese antico. Il campione conferma che la
distinzione utile non è fra lessico centrale e periferico, ma fra voci redatte
con template e voci redatte in prosa.

---

## 4. Solidità del software

### 4.1 Comportamento in condizioni avverse

Iniettando un `urlopen` fittizio — la prova che i test del progetto non fanno mai
— **cinque risposte anomale realistiche escono come traceback grezzo**, perché
`main()` non ha un handler di ultima istanza:

| risposta | esito |
| --- | --- |
| `Content-Encoding: gzip` con corpo non gzip | `gzip.BadGzipFile` non catturata |
| byte non UTF-8 | `UnicodeDecodeError` non catturata (non è sottoclasse di `JSONDecodeError`) |
| lettura troncata | `http.client.IncompleteRead` non catturata |
| `error` non è un dizionario | `AttributeError` non catturata |
| payload è una lista | `AttributeError` non catturata |
| **JSON valido senza chiave `parse`** | ritorna `None`, cioè «pagina inesistente» |
| qualunque eccezione dalla sorgente | traceback, nessun messaggio |

I codici HTTP sono invece gestiti bene: 403 e 404 falliscono subito senza
sprecare tentativi, 429 e 5xx riprovano.

L'ultima riga della tabella ha una conseguenza che va oltre il singolo comando:
quel `None` viene **memorizzato in cache con `found=0` per trenta giorni**. Un
disservizio transitorio dell'API si fossilizza in un «questa parola non esiste»
che dura un mese, e l'utente non ha modo di distinguerlo se non con `--no-cache`.

**`Retry-After` senza tetto.** Su 429 il codice onora il valore chiesto dal
server — scelta giusta — ma poi lo **raddoppia** a ogni tentativo, e non lo limita:

```text
Retry-After: 86400 con attempts=4  →  sleep(86400) + sleep(172800) + sleep(345600)
                                   →  604 800 s = 7 giorni
```

senza output dopo il primo avviso. Wikimedia usa valori di quest'ordine per i ban
temporanei. Raddoppiare un'istruzione esplicita del server è ingiustificabile
indipendentemente dal valore.

**Ricorsione senza tetto.** `cli.py:155` valida solo `--depth < 1`. La profondità
massima funzionante misurata in questo ambiente è **331**: oltre, `--depth 332`
esplode nel rendering e `--depth 900` nel walker, con `RecursionError` non
catturato. Ogni livello consuma due frame, e cinque funzioni di post-elaborazione
(`depth`, `count_nodes`, `terminals`, `_node_json`, `_subtree_lines`) sono
anch'esse ricorsive senza guardia. La probabilità che un utente digiti
`--depth 400` è bassa — il default è 12 e le catene reali arrivano a 8 — quindi è
un difetto di robustezza, non un rischio operativo.

### 4.2 Contratto della CLI

**Collisione di exit code.** `EXIT_NOT_FOUND = 2` coincide con l'exit code che
argparse usa per errore d'uso. Verificato: `etimo --bogus`, `etimo fuoco --sense abc`
e `etimo parolainesistente` escono **tutti con 2**. Uno script chiamante non può
distinguere «parola non trovata» da «ho sbagliato la sintassi» — e il sorgente
promette esplicitamente quella semantica in un commento.

**`--language` non validato**, benché `is_known_language()` esista già nel
modulo delle lingue: `etimo fuoco -l italiano` produce un generico «voce non
trovata» invece di segnalare il codice sbagliato.

**`--sense` fuori intervallo è silenziosamente ricondotto** all'ultima etimologia
disponibile, senza avviso sull'output testuale.

**`--cache-ttl` negativo è accettato**: ogni voce risulta scaduta, ma il
programma continua a scrivere su disco.

**Encoding: rischio reale ma condizionato.** L'output è interamente non-ASCII
(`√ ⊗ · ↓ ↺ └─ ├─ « »`) e non c'è `reconfigure(encoding=…)`. Con `LC_ALL=C`,
però, **non succede nulla**: Python ≥ 3.7 applica la coercizione del locale
(PEP 538/540) e l'output resta corretto, anche su pipe. Il `UnicodeEncodeError`
richiede `PYTHONIOENCODING=ascii` o la disattivazione esplicita delle protezioni.
Il finding sopravvive ridimensionato: rischio marginale, non difetto operativo.

### 4.3 Persistenza

La cache è progettata bene: memorizza anche le assenze (con test dedicato),
distingue la pagina vuota dalla pagina inesistente, usa query parametrizzate,
degrada con grazia su DB illeggibile o percorso non scrivibile proseguendo via
rete con un avviso. Tre riserve:

- **le righe scadute non vengono mai eliminate.** `_read` le ignora e ritorna
  `None`, e `INSERT OR REPLACE` le sovrascrive solo se la stessa pagina viene
  richiesta di nuovo. Le voci cercate una volta sola restano per sempre; nessun
  `VACUUM`, nessun tetto. Misurato: 256 pagine occupano 1,14 MB, di cui il 13%
  sono assenze — l'ordine di grandezza è modesto, la crescita è monotona.
- **`close()` non è mai chiamata dalla CLI** e **`stats()` non è chiamata da
  nessuna parte**: codice morto che alimenterebbe un utile `--cache-stats`.
- **`journal_mode = delete`**: due istanze concorrenti possono incontrare
  «database is locked», che viene assorbito disabilitando la cache. `WAL`
  risolverebbe il problema alla radice.

### 4.4 Rete e cortesia verso Wikimedia

Il client fa quasi tutto bene: timeout esplicito, backoff esponenziale, retry
selettivo, gzip richiesto e decompresso, intervallo minimo fra richieste basato
su `time.monotonic()` — dettaglio corretto e spesso sbagliato. Tre osservazioni:

- **lo User-Agent di default non contiene un contatto**, che le condizioni d'uso
  Wikimedia richiedono. Il README lo spiega all'utente, ma il default è ciò che
  quasi tutti useranno; basterebbe l'URL del progetto.
- **nessun riuso di connessione**: una `urlopen` per pagina significa un
  handshake TLS per pagina. Misurato però il tempo per richiesta sul corpus —
  mediana **0,88 s** contro l'intervallo di cortesia di 0,50 s — il margine non
  è tale da qualificarlo come problema di prestazioni. Va riformulato come
  questione di risorse imposte a un servizio pubblico gratuito.
- **una pagina per richiesta**, mentre l'API accetta fino a 50 titoli per
  chiamata (`action=query&titles=a|b|c`): verificato, 20 pagine e 32 KB in una
  sola richiesta. Gli antenati di uno stesso livello potrebbero essere recuperati
  in blocco.

Traffico misurato sul corpus: **360 richieste per 113 parole**, mediana 2 per
parola, media 3,2, massimo 21 (`bistecca`, catena di 8 anelli).

### 4.5 Verificabilità

Copertura reale misurata con `pytest-cov` (80 test, tutti verdi in 0,51 s):

| modulo | istruzioni | % istruzioni | **% rami** |
| --- | ---: | ---: | ---: |
| `cli.py` | 78 | **0,0** | **0,0** |
| `wiktionary.py` | 98 | **38,1** | **10,0** |
| `cache.py` | 95 | 73,5 | 72,2 |
| `walker.py` | 174 | 79,7 | 67,7 |
| `languages.py` | 44 | 85,0 | 75,0 |
| `render.py` | 145 | 88,8 | 76,9 |
| `wikitext.py` | 247 | 90,9 | 83,6 |
| `models.py` | 102 | 93,0 | 83,3 |
| **totale** | **990** | **75,3** | **67,9** |

La correlazione è esatta e va detta: **i due moduli scoperti sono esattamente
quelli in cui sono stati trovati i difetti di robustezza del §4.1**. Non è una
coincidenza retorica, è l'argomento più efficace a favore dei test.

L'ironia è che entrambi sono già progettati per essere testabili:
`main(argv) -> int` restituisce l'exit code invece di uscire, e `WiktionaryClient`
accetta `endpoint`, `min_interval`, `timeout`, `attempts` e un callback `warn`
tutti iniettabili. Manca solo qualcuno che li usi. Nessun mock HTTP esiste nella
suite: `mock`, `monkeypatch`, `responses`, `vcr` non compaiono.

### 4.6 Igiene di progetto

| | stato |
| --- | --- |
| controllo di versione | **assente** — nessun `.git`, nessuna history, nessun rollback per 3 400 righe |
| `.gitignore` | assente (`.venv/`, `.pytest_cache/`, `__pycache__/` pronti a finire nel primo commit) |
| file `LICENSE` | **assente**, benché MIT sia dichiarata in `pyproject.toml` e nel README |
| forma della licenza | `license = { text = "MIT" }` è deprecata (PEP 639 vuole `license = "MIT"`) |
| lock file | assente; `mwparserfromhell>=0.6.5` senza limite superiore |
| CI | assente; nessuna verifica che i test girino, nessuna matrice Python |
| ruff / black / mypy | **nessuno configurato**, benché il codice sia interamente annotato |
| versione | duplicata a mano in `pyproject.toml` e `version.py` |
| classifier e `[project.urls]` | assenti: il pacchetto non è pronto per la pubblicazione |

L'assenza di git è la lacuna più seria dell'elenco, e l'unica che non riguarda il
codice ma il lavoro su di esso.

---

## 5. Ciò che funziona, con altrettanta precisione

Un'analisi che elenca solo difetti non è un'analisi. Questi punti sono stati
verificati, non concessi per cortesia:

- **La separazione fra I/O e logica è disciplinata.** `render` restituisce
  stringhe e non stampa mai; il client e la cache ricevono `warn` come callback
  iniettato; `cli.py` è l'unico modulo con `print`. È ciò che rende il resto
  testabile senza mock.
- **Il `Protocol` `WikitextSource` con tre implementazioni** (rete, cache,
  dizionario) è la giuntura giusta nel punto giusto, e `DictSource` è esportato
  nell'API pubblica: il progetto è usabile come libreria.
- **La tassonomia `Terminal` con il flag `is_linguistic`** è l'intuizione
  migliore del progetto. Che sia applicata male non toglie che sia la struttura
  corretta per porre il problema — e arriva coerentemente fino al JSON, dove
  `terminal.linguistic` è un campo di prima classe.
- **Le ipotesi restano fuori dalla catena** e in JSON stanno in un campo
  separato da `ancestors`. La distinzione fra congettura e anello è mantenuta
  dove il codice la applica.
- **La provenienza è dichiarata.** Simulando la caduta della rete su un nodo
  intermedio, la catena riportata subentra *e lo dice*: «data not retrievable:
  continuing indirectly», con l'attribuzione alla voce che l'afferma. Funziona
  esattamente come promesso.
- **La distinzione dotto/popolare regge** (§3.4).
- **La normalizzazione dei titoli è fine**: macron rimossi per latino e greco ma
  non per le proto-forme, vocalizzazione rimossa negli abjad senza decomporre i
  precomposti arabi, spiriti e accenti greci preservati. Sono dettagli che
  richiedono di conoscere sia Unicode sia le convenzioni di Wiktionary.
- **La degradazione della cache è testata**, inclusi i percorsi di fallimento.
- **Nessun `except` nudo** in tutto il codice, nessun `TODO`, nessuna variabile
  globale mutabile, query SQL sempre parametrizzate, nessuna possibilità di URL
  injection (tutto passa per `urlencode`) né di path traversal (il titolo è una
  chiave SQLite, mai un percorso).
- **I test sono scritti bene**: nomi che descrivono il comportamento
  (`test_uncertain_terminal_is_a_fact_not_a_limit`), commenti che spiegano perché
  il caso esiste, fixture che riproducono la struttura reale delle voci.
- **Il README è onesto**, con numeri misurati e una sezione «Known limits» che
  dichiara limiti veri.

---

## 6. Ipotesi cadute durante la verifica

Elencarle è parte del metodo: senza, non si saprebbe quanto valgono le altre.

| ipotesi | esito |
| --- | --- |
| «Il formato legacy `{{etyl}}` tronca molte catene» | **Caduta.** 19 occorrenze in tutto il sito, zero in italiano. |
| «L'output non-ASCII rompe in locale C» | **Ridimensionata.** `LC_ALL=C` non basta: serve `PYTHONIOENCODING=ascii` o disattivare PEP 538/540. |
| «`filter_templates(recursive=False)` perde template etimologici» | **Ridimensionata.** Reale in astratto — un `{{inh}}` annidato dentro `{{q}}` viene perso — ma zero occorrenze nelle sezioni reali esaminate. |
| «La falsa incertezza in prosa sopprime il formato strutturato» | **Ridimensionata.** Il meccanismo esiste e si riproduce in laboratorio, ma sul campione di 295 sezioni l'incidenza è **0** (IC 95% 0–1,3%). Resta il difetto simmetrico, che invece è frequente: `{{unc}}` dichiarato e scavalcato. |
| «La rilevazione dei cicli è rotta» | **Ridimensionata.** Funziona: `auto` è un ciclo vero ed è gestito. Il difetto è non distinguere il ciclo dalla confluenza. |
| «La copertura di Wiktionary sul lessico regionale è povera» | **Caduta.** `'nduja` produce tre anelli corretti. |
| «Le coppie dotto/popolare non sono distinte» | **Caduta.** `vizio`/`vezzo` escono con relazioni diverse e corrette. |
| «`_data_end` è sbagliato» | **Parzialmente confutata.** Per `DATA_EXHAUSTED` l'argomento del commento regge; non regge per i tre terminali di assenza. |
| «Il mancato riuso di connessione è un problema di prestazioni» | **Riformulata.** L'intervallo di cortesia domina (0,88 s contro 0,50 s imposti). È una questione di risorse altrui, non di velocità. |

---

## 7. Raccomandazioni, per rapporto fra effetto e costo

Nessuna di queste è stata applicata: la scelta è di chi scrive il codice.

### Quanto si guadagna, misurato per lemma

Le percentuali per *sezione* dicono quanto lavora il parser; quelle per *lemma*
dicono che cosa ottiene chi cerca una parola. Misurate sul campione di 2 000
lemmi, contando l'esito della sezione che Etimo segue per default (`--sense 1`) e
tenendo separata l'onomastica (266 voci: cognomi e nomi propri, che l'utente
tipico non interroga):

**Sulle voci italiane che un'etimologia ce l'hanno** — cioè la misura di quanto
bene il programma legge la fonte quando la fonte parla:

| | copertura | IC 95% |
| --- | ---: | :---: |
| oggi | **81,7%** | 79,3–83,9 |
| + whitelist estesa (R1–R3b) | **89,0%** | 87,0–90,7 |
| + formula-guida sulla prosa (livello 3) | 90,9% | 89,1–92,5 |
| + rimando marcato (livello 2) | 92,0% | 90,3–93,5 |
| + prosa mostrata come testo (livello 1) | **98,3%** | 97,4–98,9 |
| residuo: sezioni prive di qualunque contenuto | 1,7% | |

**Su tutte le voci italiane**, incluse quelle che su Wiktionary non hanno affatto
una sezione «Etymology»:

| | copertura |
| --- | ---: |
| oggi | 52,6% |
| dopo tutti gli interventi | **63,3%** |
| **tetto assoluto** — il 35,6% delle voci non ha sezione «Etymology» | **64,4%** |

Il contributo dei tre blocchi:

| intervento | punti guadagnati | richiede inferenza? |
| --- | ---: | --- |
| estensione della whitelist (5 template più la coda) | **+7,3** | no |
| livelli 2 e 3 sulla prosa | +3,0 | sì, sulle formule |
| livello 1: mostrare il testo | **+6,3** | **no** |

Due avvertenze necessarie per leggere questi numeri.

**Il campione è uniforme sulla categoria, non pesato per frequenza d'uso.** Chi
usa lo strumento cerca lessico corrente, che su Wiktionary è redatto meglio: sul
corpus diagnostico di 113 parole scelte, la copertura odierna è già del 65,5%
contro il 52,6% del campione casuale. Le cifre della tabella sono quindi un
**limite inferiore** rispetto all'uso reale.

**Copertura non è correttezza.** Queste percentuali dicono quante voci producono
un risultato, non quante lo producono giusto. I difetti di veridicità dei §3.2 e
§3.3 — il falso `√`, le alternative concatenate, gli anelli fabbricati — sono
ortogonali alla copertura e vanno corretti a parte: R5–R10 non spostano queste
percentuali di un punto, ma sono quelli che decidono se ciò che viene mostrato è
vero.

### Effetto ampio, costo minimo — voci di dizionario e di tabella

| # | intervento | effetto stimato | dove |
| ---: | --- | --- | --- |
| R1 | `uder`→`DERIVED`, `ubor`→`BORROWED`, in whitelist e nel formato strutturato | 52 occorrenze nel campione; ≈ 3 550 voci sul sito | `wikitext.py:34-47` |
| R2 | `{{rfe}}` → `ETYMOLOGY_MISSING` (`?`), non `·` | il singolo template più frequente fra i non letti: 126 occorrenze, 7 760 voci sul sito; ripristina il principio dichiarato | `wikitext.py`, `walker.py` |
| R3 | aggiungere `confix` e `it-deverbal` (rispettivamente 31 e 11 occorrenze nel campione), poi la coda: `initialism`, `acronym`, `ellipsis`, `apheretic/apocopic/syncopic form`, `reduplication`, `rebracketing`, `semantic loan`, `named after`, `pseudo-loan`, `internationalism`, `rfv-etym` | +0,6 punti di sezioni lette, ma chiude la coda | `wikitext.py:34-67` |
| R3b | sanare gli **alias parziali**: `clip`, `dbt`, `univ`, `pref`, `noncognate`, `bf`, `onomatopoeia`, e i nomi per esteso `learned/semi-learned/orthographic borrowing` | oggi lo stesso fenomeno è letto o no secondo il sinonimo scelto dal redattore | `wikitext.py:34-67` |
| R4 | registrare `cel-gau` → Gaulish, aggiungere `la-eme` al fallback di sezione, gestire i codici multipli `a,b` | ≈ 2 200 occorrenze | `languages.py:41-223` |

### Effetto sulla veridicità — poche righe, alto valore

| # | intervento | perché | dove |
| ---: | --- | --- | --- |
| R5 | in `_data_end`, riclassificare in `RECONSTRUCTED_ROOT` **solo** `DATA_EXHAUSTED` — mai i tre terminali di assenza, mai per un codice lingua ignoto | elimina il falso `√`, §3.2.1 | `walker.py:244-252` |
| R6 | non lasciare che `{{unc}}` dichiarato sia scavalcato dalle proposte che lo seguono | `bravo`, `mafia`, `pizza`, §3.3 | `walker.py:237` |
| R7 | distinguere la confluenza dal ciclo: la chiave è fra gli antenati del percorso corrente? altrimenti usare un terminale dedicato | elimina il falso `↺`, §3.2.4 | `walker.py:337-344` |
| R8 | chiudere il corpo di `===Etymology N===` al primo sotto-heading | i discendenti non entrano più fra le ipotesi, §3.3 | `wikitext.py:136-180` |
| R9 | rimuovere le annotazioni `<…>` dai lemmi dei componenti | oggi producono titoli come `pós<t:afterwards; by>` | `wikitext.py:290-321` |
| R10 | assegnare le ipotesi anche al nodo di partenza, come già fa `_expand` | una riga; §3.2.5 | `walker.py:145-149` |

### La prosa: che cosa resta, e che cosa se ne può fare

Le **231 sezioni** che restano mute anche dopo aver esteso la whitelist (16,2% del
totale) non sono tutte «prosa da interpretare». Analizzate una per una:

| | n | quota |
| --- | ---: | ---: |
| **strutturalmente vuote**: `{{nonlemma}}` (43), nessun testo prima del sotto-heading (40), `{{lit}}` (4), `{{ety}}` senza `:relazione`, altri | **137** | 59,3% |
| **onomastica**: cognomi con formule proprie («patronymic surname from…») | 16 | 6,9% |
| **prosa vera su lessico comune** — il bersaglio | **78** | 33,8% |

Delle 78, **53 (68%) contengono già il lemma dentro `{{m}}` o `{{l}}`**: l'antenato
è marcato e certo, manca solo l'interpretazione della formula che lo introduce. E
la prosa è brevissima — mediana **18 caratteri**, il 99% sotto i 120 — quindi
mostrabile su una riga.

Le formule-guida sono poche e si dividono in due gruppi opposti:

| formula | n | effetto corretto |
| --- | ---: | --- |
| `From X`, `From X + Y`, `From the name X`, `From a shortened form of X` | 32 | **promuove** ad anello |
| `Variant of X`, `Alteration of X`, `Metathesis of X`, `Feminine of X` | 9 | **promuove** ad anello |
| `See…`, `Compare…`, `Akin to…`, `cf.` | **24** | **vieta** la promozione: sono confronti |
| `Probably…`, `Perhaps…` | 2 | ipotesi, non anello |

Il secondo gruppo è quasi grande quanto il primo. È la ragione per cui non basta
estrarre il `{{m}}` presente nella sezione: farlo senza leggere la formula
produrrebbe esattamente gli antenati falsi del §3.3. **La formula-guida serve
prima di tutto a decidere quando *non* costruire un anello.**

Ne segue una strategia a tre livelli, di costo e ambizione crescenti:

| livello | che cosa fa | copre | rischio |
| --- | --- | ---: | --- |
| 1 | quando la sezione non produce passi ma contiene testo, **mostrare il testo** sotto un terminale `?` | tutte le 231 | nullo: non asserisce nulla |
| 2 | se c'è un lemma in `{{m}}`/`{{l}}`, mostrarlo come **rimando non percorso** | 53 | basso: non è dichiarato antenato |
| 3 | riconoscere ~10 formule-guida, metà delle quali **vietano** l'anello | 41 dei 53 | medio: va testato sulle formule negative |

Il livello 1 da solo cambia la natura del problema: la sezione smette di essere un
`· dati esauriti` silenzioso e diventa «*non ho saputo interpretare: la voce dice
«From loglio»*». Costa poche righe e non può sbagliare, perché non interpreta.

### Modello — richiede una decisione, non solo una correzione

| # | intervento | perché |
| ---: | --- | --- |
| R11 | riconoscere le alternative in concorrenza («Probably… Less likely…», «either… or…») e raccoglierle come ipotesi anziché concatenarle | è il difetto che produce le affermazioni più gravi: `bravo`, `dado`, `pizza` |
| R12 | controllo di plausibilità cronologica fra lingue | intercetterebbe gran parte degli anelli fabbricati, usando dati già in tabella |
| R13 | separare «forma ricostruita» da «radice»; terminale proprio per l'origine imitativa | `*-tḗr` non è una radice; `{{onom}}` non è «dati esauriti» |

### Software

| # | intervento | perché |
| ---: | --- | --- |
| R14 | mettere il progetto sotto git, con `.gitignore` e file `LICENSE` | 3 400 righe senza history né rollback |
| R15 | test del layer HTTP con `urlopen` iniettato, test della CLI con `capsys` | sono i due moduli scoperti, e sono quelli dove stanno i difetti del §4.1 |
| R16 | handler di ultima istanza in `main()`; catturare `IncompleteRead`, `BadGzipFile`, `UnicodeDecodeError`; validare la forma del payload | cinque traceback grezzi documentati |
| R17 | tetto al `Retry-After` e nessun raddoppio del valore chiesto dal server; tetto a `--depth`; exit code applicativo diverso da 2 | §4.1 e §4.2 |
| R18 | non memorizzare come «assente» una risposta priva della chiave `parse` | evita di fossilizzare un guasto per trenta giorni |
| R19 | `ruff` e `mypy` in CI | il codice li passerebbe quasi subito, data la qualità delle annotazioni |

---

---

## 8. Dopo le correzioni

Gli interventi del §7 sono stati applicati l'11 agosto 2026 e rimisurati sullo
**stesso campione di 2 000 lemmi**, con lo stesso metodo. Nessun numero qui sotto
è una previsione: sono tutte misure ripetute.

### Copertura

| | prima | dopo | IC 95% |
| --- | ---: | ---: | :---: |
| sezioni «Etymology» da cui si ricava una catena | 69,0% | **84,6%** | 82,5–86,5 |
| lemmi con catena, fra quelli che un'etimologia ce l'hanno | 81,7% | **90,1%** | 88,2–91,7 |
| lemmi con catena **o testo mostrato** | — | **98,4%** | 97,5–99,0 |
| lemmi con catena, su tutte le voci italiane | 52,6% | **58,0%** | 55,6–60,3 |

Il tetto resta quello della fonte: il 35,6% delle voci italiane non ha alcuna
sezione «Etymology», e nessuna correzione lo cambia.

### Veridicità

I casi che avevano rivelato i difetti, rieseguiti sulle stesse voci reali:

| voce | prima | dopo |
| --- | --- | --- |
| `bravo` | `*bravus → √ radice ricostruita` | `⊗ origine incerta` + 6 proposte come ipotesi |
| `dado` | il latino `datum` discendente dall'arabo | `⊗ origine incerta` + le due alternative come ipotesi |
| `mafia` | catena verso l'arabo | `⊗ origine incerta` + l'ipotesi |
| `prete` | `√` su `*previter`, pagina inesistente | catena completa fino a `πρεσβύτερος` (grc) |
| `computer` | `· dati esauriti` | catena di 8 anelli fino al proto-italico |
| `betulla` | `√` su un titolo che non poteva esistere | catena fino al proto-indoeuropeo |
| `camoscio` | cercava la sezione «Celtic» | cerca «Gaulish», e dichiara ciò che non trova |
| `bianco` | fermo al primo anello (`la-eme`) | prosegue fino al francone |
| `tintinnare` | `· dati esauriti` | `? nessuna etimologia registrata` |
| `focus --language la` | `⊗` senza le ipotesi | `⊗` con entrambe le ipotesi attribuite |
| `allogliato` | `· dati esauriti` | `? non interpretata` + «the entry says: From loglio.» |

Il principio applicato, ora scritto nel modello e presidiato dai test: **un
terminale linguistico si emette solo su prova positiva**. Non trovare ciò che si
sa leggere non è mai, di per sé, un fatto sulla lingua. La distinzione più fine è
quella fra pagina **assente** (limite: `?`) e pagina **letta e senza etimologia**
su una forma ricostruita (fatto: `√`) — perché nel secondo caso il silenzio lo
abbiamo davvero sentito.

### Software

| | prima | dopo |
| --- | ---: | ---: |
| test | 80 | **166** |
| copertura, istruzioni | 75,3% | **89,5%** |
| copertura, rami | 67,9% | **83,7%** |
| `wiktionary.py`, rami | 10,0% | **100%** |
| `cli.py`, istruzioni | 0,0% | **80,4%** |
| segnalazioni `ruff` | non configurato | **0** |
| `mypy` | non configurato | **0 errori** |

Corretti inoltre: le cinque risposte anomale che uscivano come traceback, il
`Retry-After` senza tetto (7 giorni di attesa possibili → 60 s), la collisione
dell'exit code 2, la cache avvelenata da una risposta anomala, le righe scadute
mai eliminate, `journal_mode=WAL`, il tetto a `--depth`, la validazione di
`--language`, la connessione SQLite mai chiusa. Aggiunti `LICENSE`, `.gitignore`,
i classifier, il vincolo superiore su `mwparserfromhell`, la versione da fonte
unica e `--cache-stats`, che dà uno scopo a una funzione fino a ieri mai chiamata.

### Che cosa resta aperto

- **Il 16,2% di sezioni senza template** resta non interpretabile in catena. Il
  livello 1 (mostrare il testo) è stato applicato e le rende leggibili; i livelli
  2 e 3 — estrarre il lemma marcato, riconoscere le formule-guida — no.
- **La whitelist resta una lista chiusa** contro una fonte che cambia. Il rischio
  però non è più silenzioso: un template ignoto in una sezione altrimenti muta
  produce `? non interpretata` con il testo, non `· dati esauriti`.
- **L'ordine testuale resta un'inferenza**, corretta per le catene lineari e non
  garantita per «ultimately from X, via Y».
- **Il modello resta un albero**, e alcune etimologie non lo sono (incroci,
  contaminazioni, «merger of the 1st and 4th etymology»).
- **Il progetto non è ancora sotto git**, che resta la raccomandazione R14.

## 9. Secondo giro: i template in riga di definizione

Il 12 agosto 2026 il codice è stato riesaminato in coppia con una seconda
sessione, ciascuna sul proprio asse — questa sul lato linguistico, l'altra sul
codice. Il primo giro aveva chiuso i difetti che conosceva; questo ne ha trovata
una classe intera che non era stata vista, perché tutte le sonde del §2
guardavano dentro le sezioni «Etymology».

### 9.1 Il difetto

Com'era, prima della correzione:

```text
$ etimo tubicino
The entry «tubicino» exists but records no etymology.
This is not a gap in the tool: the data is not in the source.
```

Il wikitext di `tubicino` è, per intero: `# {{diminutive of|it|tubo|t=small tube}}`.
Quello di `far`: `# {{apocopic form of|it|fare}}`.

Il dato **c'era**, marcato in un template. Il messaggio affermava il contrario, e
lo affermava esplicitamente: *«questo non è un limite dello strumento»*. È la
stessa classe di errore del §3.2 — un limite nostro presentato come fatto sulla
fonte — sopravvissuta al primo giro perché nascosta dove nessuno guardava.

La causa è un incrocio mancato: `apocopic form of` **era già in whitelist**
([wikitext.py:106-109](src/etimo/wikitext.py#L106-L109)), ma la whitelist si
applica alla sezione «Etymology», e queste voci non ne hanno una;
`lemma_reference()` legge le definizioni, ma consultava solo la tabella dei
puntatori d'inflessione. Le due strade si sfioravano senza toccarsi.

Dopo la correzione la stessa voce dice quello che la fonte dice, e dichiara
**dove** lo dice:

```text
tubicino (it)
└─ diminutive of
   · as stated in the definition
   └─ tubo (it)
      └─ derived from Latin
         └─ tubus (la) «tube, pipe»
            └─ ? etymology not interpreted
               the entry says: «From tuba.»
```

### 9.2 Quanto valeva

Conteggi `insource:/…/` sulle voci italiane, namespace 0. Le famiglie sono state
misurate **sia col nome esteso sia con gli alias brevi**: contare solo il primo è
l'errore che ha reso necessarie due delle correzioni del §9.5.

| trattamento corretto | famiglie | voci |
| --- | --- | ---: |
| **rimando** (`asked_for`, stessa parola) | apocope (831), grafie alternative (691), superlativi (489), abbreviazioni (169), grafie medievali (95), `form of` generico, sincope, altri | **~2 440** |
| **anello** (derivazione reale) | diminutivi (461), accrescitivi (124) — al netto di quelle che una sezione «Etymology» ce l'hanno | **~50** |
| **terminale** (scioglimento come testo) | sigle (127), acronimi (21) | **~150** |
| **composto** (due sorgenti) | contrazioni (40) | **~26** |
| ⛔ **mai seguito** | `synonym of` (2 365) + `syn of` (621) | 2 986 |
| **totale intervento** | | **~2 660** |

Le cifre fra parentesi sono le voci italiane che **usano** la famiglia; quelle in
grassetto sono le voci su cui la regola **scatta**, cioè quelle prive di una
sezione «Etymology» propria. Il divario fra le due misura quanto la guardia
lavora, e varia moltissimo — misurato su campioni casuali di 50-120 voci:

| famiglia | scatta | famiglia | scatta |
| --- | ---: | --- | ---: |
| diminutivi | 2,5% | acronimi | 86% |
| `ellipsis of` | 10% | apocope | 97% |
| accrescitivi | 29% | abbreviazioni | 96% |
| `short for` | 33% | sigle | 96% |
| contrazioni | 65% | | |

I diminutivi stanno a un estremo — 56 voci su 60 una sezione «Etymology» ce
l'hanno — ed è la ragione per cui l'inferenza del §9.3 resta piccola. Le sigle e
le apocopi stanno all'altro, ed è la ragione per cui il grosso del guadagno viene
da lì.

**Un limite dichiarato di queste cifre**: il tasso di scatto è stato misurato per
le famiglie della tabella qui sopra. Per grafie alternative, grafie medievali,
superlativi e `form of` generico la proiezione assume che il template sia l'unico
contenuto della voce — normale per quelle famiglie, ma non campionato. Il totale
di ~2 660 va letto come ordine di grandezza verificato, non come conteggio esatto.

### 9.3 Le tre decisioni che hanno richiesto un giudizio linguistico

**Un template in riga di definizione è un'affermazione etimologica?** Sì per la
derivazione — non si può essere il diminutivo di X senza essere formato da X, ed
è esattamente ciò che distingue `diminutive of` da `synonym of`, che non porta
alcuna affermazione morfologica. L'inferenza che resta è un'altra: **sincronia
contro diacronia**, cioè se la formazione sia avvenuta in italiano o sia stata
ereditata già fatta (`navicella` viene dal latino *navicella*, non da *nave* +
*-cella*).

Misurata: su **237 voci** estratte a caso fra diminutivi e accrescitivi, **zero
controesempi**. La ragione è strutturale — una parola ereditata già formata *ha*
una sezione «Etymology», proprio perché qualcuno ha registrato che era ereditata,
e la guardia «solo se la voce non produce storia propria» la esclude per
costruzione. Il rischio è comunque **dichiarato nell'output** (*as stated in the
definition*) e in un campo distinto del JSON: zero su 237 non è mai.

**Apocope: anello o rimando?** Rimando. `far` non è una parola diversa da `fare`:
è lo stesso lessema con la sillaba finale caduta, condizionato dal contesto — la
forma di `andato`/`andare`, non quella di `tubicino`/`tubo`. Resta invece
`CLIPPING` quando compare nella *sezione* Etymology, dove indica l'accorciamento
**lessicalizzato** (`cinema` ← `cinematografo`). Due fenomeni omonimi, distinti
dalla posizione nella pagina.

**Acronimi e contrazioni: la forma del bersaglio decide, non la famiglia.**
`{{acronym of|it|w:it:Divisione Investigazioni Generali e Operazioni Speciali}}`
punta a una pagina di Wikipedia: trattarlo come lemma avrebbe fatto costruire un
titolo inesistente, cioè riprodotto il difetto `bnt-pro` del §3.2.2 in una
famiglia nuova. E `{{contraction of|it|da|il}}` ha **due** parametri: `dal` non
rimanda a `da`, *è* `da` + `il`. Su un campione di 50 voci per famiglia,
`abbreviation of` punta a una parola sola in 48 casi e `initialism of` a una
locuzione o a un link interwiki in 39: classificare per famiglia sbaglierebbe
entrambe le code, classificare **sulla forma del bersaglio** le prende tutte, con
un solo controllo, e protegge anche le famiglie che verranno aggiunte in futuro.

### 9.4 Il validatore cronologico, introdotto e corretto

Il §7 (R12) raccomandava un controllo di plausibilità cronologica. È stato
implementato come **nota, mai come correzione**, e ristretto all'impossibilità
anziché all'improbabilità. La prima versione ordinava le lingue per rango dentro
una famiglia, e produceva falsi positivi su prestiti reali:

```text
$ etimo banque --language fr
         └─ banca (it)
            · … the entry gives Italian as the ancestor of Middle French,
              which is the later of the two
```

`banque` e `soldat` dal francese medio all'italiano sono due casi da manuale del
prestito cinquecentesco. Il difetto: dentro la famiglia «italica» i ranghi
mescolavano una **linea verticale** di discendenza con **rami laterali sorelle** —
francese antico, francese medio e italiano non sono in rapporto antenato-
discendente, sono contemporanei. È lo stesso «confronti fra linee che non si
confrontano» che il codice diceva di evitare escludendo il protoindoeuropeo, ma
il problema si ripresenta dentro ogni famiglia appena questa si ramifica.

La correzione ha sostituito i ranghi con **intervalli di attestazione** e un solo
confronto — *il presunto antenato comincia dopo che il discendente ha cessato* —
eliminando insieme il difetto e il modello che lo produceva. Verificata su 15
coppie di controllo: **15 su 15**, con le sei catture volute conservate
(`de → lng`, `fr → la`, `en → ang`, `el → grc`, `fa → peo`, `it → la`), i cinque
falsi positivi silenziati e i tre silenzi legittimi intatti.

### 9.5 Nota di metodo: sette correzioni alle misure

Le cifre di questo giro sono state corrette sette volte prima di essere scritte.
Vale registrarlo, perché quasi ogni correzione è nata dallo stesso tipo di
errore — misurare la cosa sbagliata con lo strumento giusto:

| # | errore | effetto |
| ---: | --- | --- |
| 1 | campione preso dalla **testa della classifica** di `insource:`, non a caso | i diminutivi sovrastimati di 2,7× |
| 2 | famiglie contate col **solo nome esteso**, senza gli alias brevi | apocope 524 invece di 831, grafie 368 invece di 691 |
| 3 | lista di candidati **scritta a memoria** | 14 famiglie e 335 voci mancanti |
| 4 | regola unificata **scritta invece che misurata** | acronimi e contrazioni classificati male: due bug evitati prima dell'implementazione |
| 5 | alias brevi misurati, **nomi estesi no** | abbreviazioni 56 invece di 169, sigle 39 invece di 127 |
| 6 | `categorymembers` restituisce i primi N **in ordine alfabetico** | ogni cognome sotto «Abb-», otto locuzioni su quindici erano `100 metri`, `1000 metri` |
| 7 | contata la popolazione **«voci mute»** al posto di **«voci recuperabili»** | l'idioma col trattino dato a ~370 voci invece di ~94 |

La conclusione di fondo non si è mai spostata — la ripartizione fra ciò che
richiede un giudizio nostro e ciò che non lo richiede è rimasta intorno a 2%
contro 98% in tutte le versioni. Ma **tre volte è cambiata una conclusione**, non
le cifre:

- senza la **quarta**, `DIGOS` avrebbe interrogato una pagina inesistente e `dal`
  avrebbe perso metà della sua storia in silenzio;
- senza la **sesta**, i cognomi risultavano al 23% di risposte utili e sembravano
  il buco più grave del progetto: in realtà 25 su 40 portano `{{rfe|it}}`, cioè la
  fonte che dichiara di non aver ancora scritto l'etimologia, e il difetto
  imputabile allo strumento era di **4 voci su 120**;
- senza la **settima**, un intervento da ~94 voci sarebbe stato presentato come il
  blocco di copertura più grande rimasto, e la classe archiviata come trascurabile
  (~300 voci) sarebbe rimasta archiviata pur essendo tre volte più grande.

Due note a margine. L'errore **n. 2 e n. 5** sono lo stesso: contare un template
sotto un nome solo è **esattamente il difetto che questo intervento chiude**,
riprodotto dentro la procedura che lo misurava. E l'errore **n. 7 è il più
insidioso di tutti**, perché i primi sei producevano numeri visibilmente strani —
tutti i cognomi che cominciano per «Abb» saltano all'occhio — mentre il settimo
produceva un numero perfettamente plausibile. L'unico modo di trovarlo è stato
chiedersi *di quale popolazione* fosse la percentuale.

### 9.6 Stato del codice, giro per giro

| | §8 (primo giro) | dopo il secondo | dopo il terzo |
| --- | ---: | ---: | ---: |
| test | 166 | 234 | **262** |
| copertura, istruzioni | 89,5% | 91,9% | **92,3%** |
| copertura, rami | 83,7% | 84,7% | **85,6%** |
| `ruff`, `mypy` | 0 | 0 | **0** |

*(Il terzo giro è il §10: l'idioma del trattino, il terminale `◌` e i puntatori
multipli per parte del discorso.)*

Su un campione di 24 parole scelte per coprire i casi trattati — `tubicino`,
`far`, `DIGOS`, `dal`, `alla`, `color`, `cor`, `ben`, `mal`, `po'`, `amata`,
`andato`, `case`, più i casi storici `fuoco`, `padre`, `caffè`, `riso`, `chiesa`,
`guerra` — **24 su 24** danno una risposta utile. Sulle sole forme flesse, prima
dell'intervento erano 4 su 10.

Un risultato vale più della sua cifra: **`po'` si è risolto da solo**. Restituiva
`poi` invece di `poco` perché l'alias `apoc of` mancava dalla tabella e la
scansione saltava il sostantivo. Metà di quello che era stato classificato come
«ambiguità da progettare» era una tabella bucata.

### 9.7 Che cosa resta aperto

- **Le menzioni portanti in prosa libera** (i livelli 2 e 3 del §7) restano fuori:
  sono le uniche che richiedono un'euristica sulle formule. Il lavoro
  preparatorio è però fatto e misurato — connettivi portanti, marcatori di
  non-antenato, e le tre trappole che contengono `from` senza esserlo
  (`first attested from`, `from the same root as`, i modalizzatori
  `probably/perhaps/said to be`).
- **Un template con due bersagli separati da virgola** (`onza,oncia`) è trattato
  come terminale col testo anziché scegliendone uno: corretto, ma non ancora
  mostrato come composto.
- **Il progetto non è ancora sotto git**, che resta la raccomandazione R14.

Tre voci di questo elenco sono state chiuse nel giro successivo e sono descritte
nel §10: i puntatori multipli per parte del discorso, la classe «la fonte nomina
la lingua e tace la forma», e l'idioma del trattino.

## 10. Terzo giro: l'idioma del trattino e il terminale mancante

Il §9.7 lasciava aperte tre cose. Sono state chiuse, e una di esse ha ribaltato
la valutazione che ne era stata data.

### 10.1 Le due classi si erano invertite

Il §9.7 presentava l'idioma `{{X|it|LINGUA|-}}` come il blocco di copertura più
grande rimasto (~370 voci) e archiviava come trascurabile la classe «la fonte
nomina la lingua e tace la forma» (114 voci, 0,9%). **Erano entrambe sbagliate**,
ed è la settima correzione del §9.5:

| | dato nel §9.7 | misurato |
| --- | ---: | ---: |
| idioma, recuperabile | ~370 | **~94** |
| «lingua nominata, forma taciuta» | 114 | **~300** |

L'idioma era stato contato sulle voci **mute**, non su quelle **recuperabili**: il
trattino non promette che una forma segua. Su 120 voci estratte a caso, il 38% non
produceva nulla, ma quel 38% si divideva in tre — 18% senza alcuna menzione
(cioè la seconda classe), 10% con una menzione dal codice di lingua discordante,
e solo **9% con una menzione utilizzabile**. E la seconda classe era stata contata
su una sola delle due sintassi con cui Wiktionary scrive la stessa cosa.

Quella che era stata promossa a blocco maggiore era la minore delle due.

### 10.2 Il terminale `◌`

Per la classe da ~300 voci è stato aggiunto un terminale non linguistico:

```text
$ etimo piranha
The entry for «piranha» names where the word came from but not what it was.
That is as far as the source goes.

piranha (it)
· derived from Old Tupi, whose form the source does not give
└─ ◌ source names the language, not the form
```

Il caso ricadeva prima in `·` *dati esauriti*, marcato **fatto linguistico**, su
una situazione in cui il limite è della fonte. Il testo accanto diceva già il
vero — nulla di falso veniva affermato — ma il simbolo stava nella colonna
sbagliata di una tassonomia che il progetto usa come garanzia. I terminali sono
ora quattordici.

Un difetto emerso collegandolo: la CLI trattava quel terminale come «voce che non
porta a nulla» e stampava una diagnosi generica **al posto** dell'albero — ma
l'albero contiene la nota che *nomina la lingua*, cioè l'unica informazione che
la voce dà. Ora si stampa.

### 10.3 L'idioma, e la sua resa misurata

```text
Contardo   From the {{der|it|gem-pro|-}} elements {{m|gem-pro|*gunþiz||battle}}
                                              and {{m|gem-pro|*harduz||hard, brave}}
```

Il trattino come terzo parametro è il modo documentato di dire «derivato da questa
lingua, la forma la do a parte». Il legame non richiede di interpretare la
formula: **la menzione che segue porta lo stesso codice di lingua**. La regola
implementata raccoglie le menzioni successive finché il codice corrisponde e si
ferma alla prima che non corrisponde — così i cognati chiudono la raccolta da
soli, senza dover elencare che cosa la interrompe.

La promozione avviene dentro il parsing del corpo e produce passi ordinari,
quindi passa per l'ordine di autorità già scritto. Le tre cautele previste sono
tenute dai dati:

| voce | struttura | esito |
| --- | --- | --- |
| `Contardo` | due menzioni, stesso codice | composto, due rami fino al PIE |
| `Aosta` | una menzione, poi cognati | si ferma prima dei cognati |
| `brezza` | `{{unc}}` + menzione dal codice discordante | nulla promosso, tutto fra le ipotesi |
| `piranha` | nessuna menzione | `◌` |

**Resa, misurata dopo l'implementazione.** Le dieci voci che la sonda aveva
indicato come recuperabili costruiscono ora tutte una catena — `Contardo` →
`*gunþiz` più `*harduz`, `camposanto` → `campus sanctus`, `tramezzo` →
`intrā medium` — cioè **dieci su dieci**. Su un campione casuale fresco della
stessa popolazione le catene passano dal 62% al 70%, che proietta **~80 voci
recuperate**.

Le due misure vanno lette per quello che sono: **la prova appaiata è l'evidenza**,
il dato di popolazione ne conferma l'ordine di grandezza e nulla di più. Gli 8
punti di scarto vengono da due estrazioni indipendenti di 120 voci, dove
l'intervallo al 95% è di circa ±8 punti: presi da soli non sarebbero separabili
dal rumore.

### 10.4 Una lacuna di prova, trovata dalla copertura

Il terzo giro ha fatto **scendere** la copertura pur aggiungendo test: da 91,9% a
89,8% sulle istruzioni, con il calo quasi tutto in `cli.py` (83,6% → 71,6%).

La causa: `_pick_target`, la funzione dietro `--as`, non aveva **un solo test**,
mentre `_pick_sense` — che fa la stessa cosa per i sensi — ne aveva sei. E aveva
una superficie che il gemello non ha: il confronto per nome con `casefold()`, su
un'opzione che l'utente digita a mano invece di sceglierla da un elenco numerato.

Dieci test l'hanno chiusa, fra cui i tre casi che nessuno toccava — `--as POCO`
equivalente a `--as poco`, un nome inesistente che esce con codice 3 anziché
ripiegare in silenzio, e `EOFError` sul prompt che non è un crash. Uno di essi,
scritto come `assert … or True`, non poteva fallire: intercettato da `ruff` e
rimosso. **Un test che non può fallire è peggio di un test assente**, perché conta
nella copertura e rassicura a vuoto.

È il motivo per cui la metrica è servita: non «manca copertura», ma *il gemello ne
ha sei e questo zero, e ha una superficie in più*.

### 10.5 Il confine fra le due voci, reso visibile

Restava un'osservazione senza risposta: un utente italiano vede una schermata in
cui **tutto** è inglese, e non ha modo di distinguere ciò che Wiktionary afferma
da ciò che etimo commenta. Le glosse sono citazioni e tradurle significherebbe
inventare; ma «inherited from Latin», «data exhausted», «as stated in the
definition» sono parole dello strumento, non della fonte.

La soluzione adottata non traduce nulla e marca il confine **due volte**: ciò che
viene dalla fonte è in corsivo ciano *e* fra «guillemets»; ciò che dice etimo non
lo è. La ridondanza è la parte utile — il colore sparisce con `NO_COLOR`, in una
redirezione su file, in un terminale povero, in un testo incollato altrove, e la
punteggiatura no.

## 11. Quarto giro: la metrica era sbagliata

I tre giri precedenti hanno misurato la **copertura** e l'hanno portata al 90% fra
le voci che un'etimologia ce l'hanno. Nessuno ha misurato la **correttezza**.

Il §7 lo diceva: *«Copertura non è correttezza. Queste percentuali dicono quante
voci producono un risultato, non quante lo producono giusto.»* Poi il documento
non ci è più tornato — e delle 19 raccomandazioni del §7, **solo 2 sono ricitate
dopo il §8**.

### 11.1 Il caso che ha aperto il giro

L'autore ha interrogato `cavolo`. Ha ottenuto:

```text
cavolo (it) ← caulus (la-lat) ← cavolo (nap) ← caulis (la) ← *keh₂ulis (ine-pro)
```

Il napoletano non è antenato del latino tardo: è una varietà italoromanza che dal
latino discende. La voce dice:

> `{{der+|it|la-lat|caulus}}, from {{der|it|la|caulis}}, through a southern
> Italian language.` **`Possibly`** `{{bor|it|nap|cavolo}}` **`or`**
> `{{bor|it|scn|cavulu}}.`

**La voce è scritta meglio del programma.** Dichiara il certo, marca il probabile,
offre due alternative senza sceglierne una. Etimo ha scelto, ha fatto sparire il
siciliano, e ha disegnato l'anello **pur avendo rilevato l'impossibilità**: il
validatore cronologico del §10 scriveva la nota e la catena usciva lo stesso.

È **R11**, la raccomandazione che il §7 definiva *«il difetto che produce le
affermazioni più gravi: bravo, dado, pizza»*. Era stata applicata solo dove
l'incertezza sta in un template. `pizza`, citata nella raccomandazione stessa,
produceva ancora una catena inventata.

### 11.2 La diagnosi, che vale per tutti i difetti insieme

| | la fonte dava | etimo voleva | ha prodotto |
| --- | --- | --- | --- |
| `cavolo` | due congetture | una catena | ha scelto, e ha nascosto l'altra |
| `banale` | una forma annotata | un anello da seguire | `*h₂el-<t:to grow><id:grow>` → falso «nessuna voce» |
| `zucchero` | un codice fuori tabella | un'etichetta di lingua | `pgd:𐨭𐨐𐨪` dato per persiano medio |

**La falsità entra nel momento esatto in cui etimo smette di riportare e comincia
a estrapolare.** Sempre. In nessuno dei casi il dato della fonte era sbagliato.

E la conseguenza scomoda: **la copertura e la correttezza tiravano in direzioni
opposte.** Ogni punto di copertura guadagnato oltre il nucleo inequivocabile era
un punto di estrapolazione aggiunto. Il 90% del §8 e i difetti di questo capitolo
sono lo stesso fatto guardato due volte.

### 11.3 La popolazione, ridefinita

Le misure precedenti giravano su «voci italiane», che sono 597 727 — ma il 78%
sono **forme flesse**, che un'etimologia non la affermano affatto e che gonfiano
al ribasso qualunque tasso d'errore. La popolazione che conta è un'altra:

| | voci |
| --- | ---: |
| lemmi italiani | 129 650 |
| − polirematiche | 119 009 |
| − nomi propri (cognomi inclusi) | 102 929 |
| − acronimi, sigle, abbreviazioni | **102 692** |

Calcolate con esclusioni incatenate e non per sottrazione: le categorie si
sovrappongono, e sommarle darebbe 28 127 esclusioni contro le 26 958 reali.

E su quelle 102 692, che cosa dice la fonte (campione casuale, n = 1500):

| | % | proiezione | serve interpretare? |
| --- | ---: | ---: | --- |
| solo template, nessuna prosa qualificante | 54,2% | ~55 700 | **no** — si parsa e si stampa |
| nessuna sezione «Etymology» | 35,1% | ~36 100 | **no** — dirlo è fedele |
| **servibile senza interpretare nulla** | **89,3%** | **~91 800** | |
| template + prosa che li qualifica | 3,9% | ~4 000 | **sì** |
| template + prosa residua, ambigua | 3,9% | ~4 000 | in parte |
| template che etimo non legge | 2,7% | ~2 800 | no, lavoro di tabella |

**L'11% che resta non va risolto: va dichiarato.** «La voce dice: *Possibly from
Neapolitan cavolo or Sicilian cavulu*» è una risposta fedele, utile, e impossibile
da sbagliare.

### 11.4 Le quattro regole, tutte sottrattive

1. Nessun anello che la fonte non affermi **senza condizioni**.
2. Dove la fonte condiziona, si riporta la condizione e **non si concatena**: le
   forme coinvolte diventano ipotesi, non figli.
3. Una forma che non si estrae pulita **si stampa e ci si ferma**: mai costruire
   un titolo di pagina da una stringa che contiene ancora markup.
4. Nessun terminale linguistico senza aver letto la pagina.

Corollario: **una contraddizione cronologica rilevata declassa l'anello a
ipotesi.** Il §10 la annotava e la disegnava; segnalare non basta, perché un
legame che il programma ha già dimostrato impossibile non può stare nell'albero.

### 11.5 Che cosa producono, sui casi che le hanno motivate

```text
cavolo (it)
· doublet of «caule»
perhaps cavolo (nap) — «through a southern Italian language. Possibly»
perhaps cavulu (scn)
└─ derived from Late Latin
   └─ caulus (la-lat)
      └─ derived from Latin
         └─ caulis (la)
            └─ derived from Proto-Indo-European
               └─ *keh₂ulis (ine-pro) «straight stalk»
```

Il certo è catena, il probabile è congettura **con le parole della fonte**, e
nessuna alternativa sparisce.

| voce | prima | dopo |
| --- | --- | --- |
| `cavolo` | il napoletano come anello | catena corretta + due congetture |
| `banale` | `*h₂el-<t:to grow><id:grow>` → falso «nessuna voce» | `*h₂el-` |
| `zucchero` | `pgd:𐨭𐨐𐨪` dato per persiano medio | `𐨭𐨐𐨪` (pgd) |
| `pizza` | catena verso il greco bizantino, sola | la stessa catena + `bizza` (lng) come ipotesi |
| `pillacchera`, `arnia` | catene costruite su prosa dubitativa | `⊗ origine incerta` |

E **nessuna regressione**: dodici catene già verificate corrette sono rimaste
intatte — `padre` → `patre` → `pater` → `*patēr`, `prete` → `preite` →
`*previter` → `presbyter`, `betulla` → `*bitu` (gallico), `chiesa` → `ecclēsia` →
`ἐκκλησία`. Era il rischio proprio delle regole sottrattive, e non si è
materializzato.

Due difetti sono emersi solo implementando, ed erano peggiori del bersaglio:
`parse()` faceva `hypotheses = …` invece di `+=`, cancellando le congetture
appena raccolte; e il renderer stampava le ipotesi **solo sotto un terminale**,
quindi un nodo con figli *e* congetture — cioè esattamente `cavolo` — le perdeva.
Senza quelle due correzioni, tutto il lavoro sui marcatori sarebbe stato
invisibile.

### 11.6 La misura: sette controlli senza dizionario

Il difetto di processo che ha lasciato passare `cavolo` non è tecnico: R11 fu
scritta, classificata come la più grave, e poi non tracciata più. Il rimedio è che
la correttezza smetta di essere una dichiarazione e diventi una **misura ripetibile**.

Sette predicati che rilevano un difetto **dall'output stesso**, senza dizionario
di riferimento e senza giudizio linguistico:

| | controllo | caso che lo motiva |
| --- | --- | --- |
| C1 | il lemma contiene markup | `banale` |
| C2 | prefisso di lingua non spezzato, lingua ereditata | `zucchero` |
| C3 | ordine impossibile **e** anello disegnato | `cavolo` |
| C4 | marcatore che condiziona, e output senza ipotesi | `cavolo`, `pizza` |
| C5 | forma nominata dalla fonte e assente dall'output | il siciliano di `cavolo` |
| C6 | terminale linguistico su una pagina mai letta | il principio del §8 |
| C7 | stessa forma e stessa lingua due volte nello stesso ramo | ciclo mascherato |

**Un controllo che non si accende sul proprio caso è rotto**, quindi ognuno porta
il suo caso reale come test.

**C6 non si accende mai, ed è una buona notizia**: costruendo i due casi limite si
vede che una proto-forma senza pagina dà `ENTRY_MISSING` (limite) e una con pagina
muta dà `RECONSTRUCTED_FORM` (fatto). La distinzione del §8 regge; C6 resta come
guardia di regressione su un invariante che oggi non è violato.

### 11.7 L'unica eccezione dichiarata al principio

Il §8 stabiliva: *pagina assente → limite `?`; pagina letta e muta → fatto `√`*.
C6 ha mostrato che per **`RECONSTRUCTED_ROOT` la pagina non si legge mai**, e il
terminale è comunque marcato linguistico.

Non è una svista, ed è giusto così: **una radice non è una parola con una storia
propria**, è l'elemento astratto da cui le parole si formano. «Qual è l'etimologia
di `*ḱel-`?» non è la domanda ben posta che è «qual è l'etimologia di `*patēr`?».
La prova positiva esiste ed è il `{{root}}` della voce — non il silenzio di una
pagina che nessuno ha aperto.

Ma era un'eccezione **dedotta**, non dichiarata, e ora è scritta nel commento del
terminale. E C6 la esenta: un controllo che si accende per sempre su un
comportamento corretto diventa il rosso per abitudine, cioè quello che si smette
di leggere.

Verificandola è però emerso un difetto vero, che senza quel controllo sarebbe
rimasto latente:

```text
lemma mostrato      *ḱel- (cover)
titolo costruito    Reconstruction:Proto-Indo-European/ḱel- (cover)   ASSENTE
pagina reale        Reconstruction:Proto-Indo-European/ḱel-           esiste
```

Il disambiguante fra parentesi — chiarimento redazionale per distinguere radici
omonime — finiva **dentro il lemma**, stessa famiglia di `<t:>` e `<id:>`. Non
faceva danno solo perché le radici non si pescano mai: il giorno in cui qualcuno
le rendesse percorribili sarebbero **891 falsi «nessuna voce»**. È il difetto che
aspetta, latente finché non cambia una riga altrove.

### 11.8 Tre volte lo strumento di misura ha accusato il codice a torto

Le sette correzioni del §9.5 riguardavano le cifre. Queste tre riguardano
qualcosa di peggio: **il misuratore che segnala un difetto inesistente.**

| # | l'errore | quanto gonfiava |
| ---: | --- | --- |
| 8 | **C5 contava** le relazioni dichiarate contro le forme mostrate | 5 voci sane su 14 accusate |
| 9 | l'**estrattore** della sonda generativa non conosceva tutte le sintassi con cui la fonte nomina una forma | 6 segnalazioni su 7 false |
| 10 | il **walker condiviso** fra le voci del campione: una pagina già scaricata non veniva richiesta di nuovo, e il registro per-voce la leggeva come «mai letta» | **C6 dal 25% allo 0,8%** |

Tutte e tre **gonfiavano il difetto, mai il contrario**. Un misuratore che sbaglia
in modo asimmetrico non produce rumore: produce un **bias**. Nel nostro caso era
quello prudente — accusava il programma di essere peggiore di quanto fosse — ma
per fortuna, non per costruzione.

La n. 10 è la più insidiosa delle tre, e per una ragione precisa: le prime due
erano estrattori incompleti, cioè strumenti che non sapevano abbastanza. Questa
era uno strumento **che misurava male perché il programma si comportava bene** —
la cache di sessione faceva esattamente il suo lavoro, e il controllo la scambiava
per un'affermazione senza prova.

E la n. 8 dice qualcosa di più: **l'ambiguità che il progetto esiste per tenere
separata — una catena di tre contro tre alternative — era ricomparsa dentro lo
strumento costruito per misurarla.**

Da cui la conclusione di metodo che vale più delle singole correzioni: **uno
strumento di misura scritto dalla stessa testa che ha scritto il programma eredita
gli stessi punti ciechi.** Qui ha funzionato solo perché i punti ciechi erano
*diversi*: le tre correzioni sopra sono errori di chi misurava, ed emergevano
perché il codice misurato l'aveva scritto un altro. Essere in due non basta —
serve che i due lavorino su lati diversi dello stesso oggetto.

### 11.8.1 L'ottava, in dettaglio

C5 era stato scritto come *«relazioni dichiarate nella fonte > forme mostrate
nell'output»*. Si accendeva su `chiesa`, `guerra`, `piazza`, `caffè`,
`formaggio` — voci sane.

Il motivo: **«From X, from Y, from Z» dichiara tre relazioni e produce un figlio
diretto solo**, perché le altre due si raggiungono camminando. Contando, una
**catena** di tre e tre **alternative** sono indistinguibili. È esattamente
l'ambiguità che ha prodotto `cavolo`, ricomparsa **dentro lo strumento costruito
per misurarla**.

La versione che funziona confronta **identità, non numeri**, con due accorgimenti
trovati sui falsi allarmi:

- **normalizzare i diacritici**: la fonte scrive `πλατεῖα` dove la voce si intitola
  `πλᾰτεῖᾰ`, e `نارنگ` contro `نَارَنْگ`. Sono segni redazionali, non parte della parola;
- **non confrontare il codice di lingua**: la fonte dice `fa` e l'output risolve
  `fa-cls`, la fonte `la-med` e l'output `la-eme`. Una forma davvero persa
  sparisce del tutto, non cambia etichetta.

### 11.9 La misura, su 500 voci a caso dei 102 692

Eseguita contro il codice corretto, con sorgente e walker nuovi per ogni voce:

| | voci | % | proiezione | IC 95% |
| --- | ---: | ---: | ---: | :---: |
| **nessuna anomalia** | **494** | **98,8%** | **~101 500** | 100 000–102 100 |
| almeno un'anomalia | 6 | 1,2% | ~1 230 | 570–2 660 |
| C1 lemma con markup | 0 | 0% | — | 0–780 |
| C2 prefisso non spezzato | 0 | 0% | — | 0–780 |
| C3 ordine impossibile disegnato | 0 | 0% | — | 0–780 |
| C4 congettura data per fatto | 3 | 0,6% | ~620 | 210–1 800 |
| C5 forma dichiarata e persa | 5 | 1,0% | ~1 030 | 440–2 380 |
| C6 terminale senza lettura | 0 | 0% | — | 0–780 |
| C7 ciclo mascherato | 0 | 0% | — | 0–780 |

**Cinque controlli su sette a zero.** Sono i difetti di `banale`, `zucchero`,
`cavolo`, `pizza` e delle radici — cercati su un campione che non li conteneva.

Il residuo è di due tipi soli:

```text
C4  dipelare «either/or»   brindare «probably»   rodomonte «apparently»
C5  mansezza  → mansuetudine (it)      decenario → dēnārius (la-cla)
    dipelare  → dēpilō (la)            brindare  → bring dir's (de)
```

**Due delle sei segnalazioni non reggono all'esame, e vanno tolte.**

`aritmetica` (C5): la fonte scrive `ἀριθμητική (τέχνη)`, con il sostantivo
sottinteso fra parentesi, e l'output mostra il solo `ἀριθμητική` — **che è il
lemma**. È lo stesso fenomeno del disambiguante `(cover)` del §11.7: la parentesi
non fa parte della forma, e chiedere all'output di riprodurla significherebbe
chiedergli una stringa che il titolo di pagina non ha.

`brindare` (C4): la fonte dice *«…, probably introduced by German mercenaries in
the 16th c.»*. Il modalizzatore **non governa un etimo**: governa una circostanza
storica, il *come* del prestito. La catena `brindare < sp. brindar < ted. bring
dir's` è asserita senza condizioni, ed è quella che l'albero mostra.

Ne esce una distinzione che nessuno dei due aveva formulato, e che vale per la
lista dei marcatori in generale: un modalizzatore può governare un **etimo**
(«probably *from* X») o una **narrazione di trasmissione** («probably
*introduced by*», «*brought by*», «*spread through*», «*coined by*»). **Solo il
primo condiziona.** Un ambito che si estende in avanti dal marcatore fino al punto
fermo lo distingue da sé: fra `probably` e il punto, in `brindare`, non c'è alcun
template di relazione da declassare.

Il residuo vero è dunque **C4 = 2 (~410 voci)** e **C5 = 4 (~820)**: in tutto
**~1 % delle voci**, tutte dentro l'intervallo già dichiarato.

Le quattro che restano sono difetti reali e di due sole forme:

| voce | difetto |
| --- | --- |
| `rodomonte` | «*apparently from* {{af\|it\|rodo\|monte}}» dato per fatto: il condizionamento non copre i template di **formazione** |
| `dipelare` | «{{af\|…}} **or** from {{inh\|…}}»: alternanza **fra** due template, non prima di uno |
| `mansezza`, `decenario` | forma dichiarata dalla voce e non mostrata (§11.10) |

### Come va letto questo numero

Non è «quanti difetti ci sono». È **«quanti difetti, fra quelli che sappiamo
cercare, restano visibili oggi»**. Le tre parole in corsivo non sono cautele
formali: ciascuna toglie qualcosa alla lettura ingenua.

**«fra quelli che sappiamo cercare».** I sette controlli nascono ciascuno da un
caso che qualcuno aveva guardato a mano. Trovano bene ciò che conoscono e per
costruzione nient'altro. Ogni difetto corretto in questa giornata è venuto da
un'ispezione — `cavolo` dall'autore, `banale` e `zucchero` dalla verifica
linguistica, `pizza` da un fixture ampliato, le radici da una sonda generativa,
`billia` da una nota che qualcuno ha letto. **Nessuno da un campione casuale.**

**«visibili».** Un difetto può esistere e non essere osservabile. Il caso di
`polistrumentalista` stava nel programma da sempre: la riserva conteneva un'analisi
sincronica che non doveva starci, e **nessuno poteva accorgersene finché quella
riserva veniva scartata in silenzio**. È stato un meccanismo che *stampa* invece
di buttare a renderlo visibile — cioè un miglioramento, non una misura.

**«oggi».** Tre campioni successivi sulle stesse funzioni — 60, 80 e 100 voci —
hanno trovato ciascuno una classe di errore che il precedente **non poteva**
trovare. Non erano campioni troppo piccoli: **l'insieme dei difetti osservabili si
muoveva sotto di essi**, perché ogni correzione cambiava ciò che era visibile.

Il numero è quindi un fotogramma, non un bilancio. Vale nella misura in cui si
dichiara che cos'è.

### 11.10 Una classe di difetto di segno opposto

```text
formaggio  →  la fonte nomina «fōrma (la)», l'output non la mostra mai
```

La voce dice per intero *«from Old French fromage, from Late Latin formaticum,
**from Latin forma**»*. Etimo segue `fromage`, arriva a `fōrmāticum` che non ha
voce, e si ferma: `fōrma`, **già dichiarata dalla voce di partenza**, sparisce.

Non è un anello inventato: è un anello **dichiarato e perso**. La causa è la
propagazione della riserva di passi, azzerata quando il cammino passa a una pagina
nuova. Sotto la metrica nuova conta quanto l'altro difetto — la fedeltà si perde
tanto aggiungendo quanto togliendo — e resta aperta.

### 11.11 Cinque forme di uno stesso difetto

I difetti chiusi in questo giro non erano cinque cose diverse. Erano **cinque
modi in cui un programma può affermare qualcosa che non sa**, e vale la pena
elencarli perché il sesto non lo conosciamo ancora.

**L'invariante che li tiene insieme** — nella formulazione che ne è uscita:

> **Se il programma può scrivere una nota che contraddice il proprio albero,
> l'albero è sbagliato.** Non esiste un caso in cui la nota sia il posto giusto
> per la contraddizione.

Perché ogni volta la nota diceva il vero e la struttura il falso — e la struttura
è quella che il lettore legge. Annotare *sembrava* la scelta prudente, perché non
butta via nulla; ma una nota accanto a un'affermazione falsa non la corregge, le
aggiunge una postilla che si può saltare.

**Le prime quattro forme descrivono uno stato:**

| | dove | i due canali |
| ---: | --- | --- |
| 1 | cronologia | la nota diceva «Neapolitan is the later of the two», l'albero disegnava il napoletano come antenato |
| 2 | prosa condizionante | la fonte diceva «Possibly … or …», l'albero ne prendeva una come fatto |
| 3 | cicli | il simbolo diceva `↺`, l'albero disegnava «πίτα discende da πίτα» |
| 4 | **la stessa regola in più posti** | nessuna contraddizione visibile: due funzioni identiche di cui una aggiornata e una no |

La quarta è la più insidiosa delle quattro, perché i punti **non si guardano
affatto**: il difetto non si manifesta come contraddizione ma come una funzione
che si comporta bene e una identica accanto che no. `-ιστής` girava sbagliato da
quando era stato scritto `_spellings`, e non l'ha preso nessun test — l'ha preso
un campione casuale. Il `code:lemma` è andato così **tre volte**, e chi scrive
questo documento l'ha commessa una quarta nel proprio strumento di misura,
**un'ora dopo averla diagnosticata**.

### La quinta forma descrive invece una transizione

Il 13 agosto gli acronimi sono usciti dall'ambito del progetto. Poche ore prima
era stato aggiunto un accorgimento **per loro**: rimuovere il prefisso interwiki
da `w:it:Divisione Investigazioni…`, che sporcava il testo dell'espansione.

Tolti gli acronimi, quel prefisso è **l'unica cosa che segnala che il bersaglio
non è un lemma**: i due punti lo fanno classificare come locuzione. Senza,
`w:it:Roma` sarebbe diventato una richiesta a Wiktionary per una pagina che non
può esistere, letta come «nessuna voce» — il difetto `bnt-pro` del §3.2, alla
terza comparsa con un vestito diverso.

**Codice corretto che diventa sbagliato senza essere toccato**, perché cambia ciò
che gli sta intorno. Tre ore fra la scrittura e il momento in cui era un difetto.

E ha una proprietà che le prime quattro non hanno: **nessun test lo prende.** Al
momento della scrittura il codice era giusto e i suoi test lo confermavano —
quello strip ne aveva due, verdi. **Sono morti insieme alla funzione che
coprivano**, e una suite intera sarebbe rimasta verde mentre il difetto entrava,
perché nessuno dei suoi test parlava del *rapporto* fra le due cose.

Da cui la regola operativa, che non è «rileggi il codice quando togli una
funzione»:

> **Rileggi il codice che era stato aggiunto *per* quella funzione — i suoi test
> se ne vanno con lei, e non ti avvertono.**

### E lo stesso vale per le parole, non solo per il codice

Nello stesso giro, questo messaggio è diventato falso senza che nessuno lo
toccasse:

```text
prima   This is not a gap in the tool: the data is not in the source.
dopo    The source may state none, or state it in a form not read here.
```

Per `S.p.A.` il dato **è** nella fonte — `{{abbreviation of|it|società per
azioni}}` — e siamo noi a lasciarlo stare. Era diventato **esattamente un limite
nostro travestito da silenzio della fonte**, cioè la cosa che l'intero progetto
esiste per non dire, dentro la frase che la nega.

Nessun errore di scrittura, nessun difetto di lettura: **una frase corretta che il
mondo intorno ha reso bugiarda.** L'invariante va quindi riletto a ogni
cambiamento di **ambito**, non solo a ogni cambiamento di codice — e un controllo
di coerenza non l'avrebbe presa, perché il messaggio era coerente con sé stesso e
falso rispetto a ciò che il programma aveva smesso di fare.

## 12. Il conto delle raccomandazioni, chiuso

Il §7 conteneva 20 raccomandazioni. Dal §8 in poi **solo due erano state
ricitate**, ed è il difetto di processo che ha lasciato passare `cavolo`: R11 era
scritta, classificata come la più grave, e mai più tracciata.

Verificate una per una contro il codice, ciascuna con la prova eseguibile:

| | intervento | esito |
| --- | --- | --- |
| R1 | `uder` e `ubor` in whitelist | **applicata** |
| R2 | `{{rfe}}` → terminale di assenza | **applicata** |
| R3 | `confix`, `ellipsis`, `reduplication`, `rebracketing`… | **applicata** ¹ |
| R3b | alias parziali: `clip`, `dbt`, `bf`, `univ`… | **applicata** |
| R4 | `cel-gau`, `la-eme`, codici multipli | **applicata** |
| R5 | `_data_end` riclassifica solo `DATA_EXHAUSTED` | **applicata** |
| R6 | `{{unc}}` non scavalcato dalle proposte | **applicata** |
| R7 | confluenza distinta dal ciclo | **applicata** |
| R8 | sezione chiusa al primo sotto-titolo | **applicata** |
| R9 | annotazioni `<…>` fuori dai lemmi | **applicata** |
| R10 | ipotesi anche sul nodo di partenza | **applicata** |
| R11 | alternative in concorrenza → ipotesi | **applicata** (§11) |
| R12 | controllo di plausibilità cronologica | **applicata** (§10, corretta in §11) |
| R13 | forma ricostruita ≠ radice; origine imitativa | **applicata** |
| **R14** | **git, `.gitignore`, `LICENSE`** | **aperta** |
| R15 | test del layer HTTP e della CLI | **applicata** |
| R16 | handler di ultima istanza; eccezioni HTTP | **applicata** |
| R17 | tetto a `Retry-After` e a `--depth`; exit code ≠ 2 | **applicata** |
| R18 | risposta senza chiave `parse` non memorizzata come assente | **applicata** |
| **R19** | **`ruff` e `mypy` in CI** | **aperta** |

¹ **Nota, 13 agosto 2026 — gli acronimi sono usciti dall'ambito del progetto.**
`{{acronym of}}`, `{{initialism of}}` e `{{syllabic abbreviation of}}` non sono
più letti, e il terminale `⊙` non esiste più. La ragione non è tecnica: **un
acronimo non discende dalla propria espansione, la scrive.** `CEI` non viene *da*
«Conferenza Episcopale Italiana», la **è**, in lettere — è una questione di
grafia, non di storia, e questo strumento risponde a una domanda sola.

Le **abbreviazioni** restano, perché sono un'altra cosa: `{{abbreviation of|it|
società per azioni}}` nomina una parola che una storia ce l'ha. Che togliere le
prime non abbia portato via le seconde è il merito della regola del §10 — decidere
sulla **forma del bersaglio** e non sulla famiglia del template. Classificando per
famiglia, la rimozione avrebbe travolto anche le abbreviazioni.

Il documento cita gli acronimi anche altrove (§9.2, §10.2, §11) e quelle
occorrenze **restano**: sono il registro di ciò che è stato misurato quando lo è
stato, non una descrizione dello stato corrente.

**Se un giorno rientrassero, l'ambiguità va progettata per prima.** `CEI` ha
**due** espansioni su Wiktionary — Conferenza Episcopale Italiana e Comitato
Elettrotecnico Italiano — e il codice rimosso prendeva la prima **in silenzio**,
mentre i puntatori con più bersagli vengono offerti come scelta fin da `po'`
(§10). Era lo stesso difetto vestito da un template diverso, ed è rimasto
invisibile tanto a lungo per la ragione che questo giro ha incontrato quattro
volte: **nulla stampava mai quello che veniva scartato.**

**Diciotto su venti.** Le due aperte sono in realtà una: **R19 non è eseguibile
finché R14 non lo è**, perché non esiste una CI senza un repository. Il codice
passa `ruff` e `mypy` puliti a ogni esecuzione locale; manca il luogo dove farlo
girare da solo.

La verifica si riproduce importando le tabelle del progetto e interrogandole —
`"uder" in _LINEAR_RELATIONS`, `hasattr(Terminal, "RECONSTRUCTED_FORM")`,
`parse("{{der|it|la|x<t:y>}}").steps[0].forms[0].lemma == "x"` — così il conto
non è una dichiarazione ma una misura, ripetibile il giorno in cui qualcuno
sospetti che una sia regredita.

## Appendice · Riproducibilità

Le sonde usate per questo documento sono script autonomi che non toccano il
repository. Le misure principali si riproducono così:

```bash
# copertura reale
PYTHONPATH=src python -m pytest tests --cov=etimo --cov-branch

# conteggio delle transclusioni (una richiesta per pattern)
#   action=query&list=search&srsearch=insource:/\{\{uder\|it\|/&srinfo=totalhits

# falso terminale da template non riconosciuto
python -c "from etimo.wikitext import parse; print(parse('{{ubor|it|en|computer}}','it').steps)"   # []

# falso « radice ricostruita » su voce assente
python -c "
from etimo.walker import Reconstructor; from etimo.wiktionary import DictSource
p={'avus':'==Latin==\n\n===Etymology===\nFrom {{inh|la|itc-pro|*awos}}.\n'}
t=Reconstructor(DictSource(p)).reconstruct('avus','la').start.terminals()[0].terminal
print(t.name, t.is_linguistic)"                                    # RECONSTRUCTED_ROOT True

# profondità massima prima del RecursionError: ricerca binaria su max_depth
# eccezioni non catturate: sostituire urllib.request.urlopen con una risposta fittizia
```

Le misure del §9 usano tre sonde aggiuntive, tutte fondate su `insource:/…/` con
`srsort=random` dove serve un campione e non una classifica:

```bash
# quante voci una famiglia copre, contando SEMPRE nome esteso e alias brevi
#   insource:/\{\{apocopic\sform\sof\|it\|/   e   insource:/\{\{apoc\sof\|it\|/

# su quali voci la regola scatterebbe: campione casuale, poi presenza di «Etymology»
#   list=search&srsort=random  +  prop=revisions&rvslots=main  (50 titoli per richiesta)

# forma del bersaglio: parola sola, locuzione o link interwiki
#   \{\{(abbreviation|initialism)\sof\|it\|([^|}]*)   →  " " nel valore? ":" nel valore?
```

```python
# il caso del §9.1, senza rete: la derivazione sta nella riga di definizione,
# la voce non ha una sezione «Etymology», e prima non ne usciva nulla
from etimo.walker import Reconstructor
from etimo.wiktionary import DictSource
pagine = {
    "tubicino": "==Italian==\n\n===Noun===\n{{it-noun|m}}\n\n"
                "# {{diminutive of|it|tubo|t=small tube}}\n",
    "tubo": "==Italian==\n\n===Etymology===\nFrom {{inh|it|la|tubus}}.\n",
}
nodo = Reconstructor(DictSource(pagine)).reconstruct("tubicino", "it").start.children[0]
print(nodo.relation.name, nodo.form.lemma)          # DIMINUTIVE tubo

# i falsi positivi del §9.4, sulle 15 coppie di controllo
from etimo.languages import impossible_order
print(impossible_order("it", "frm"))                # False: prestito reale
print(impossible_order("de", "lng"))                # True: impossibile
```

Il corpus diagnostico (113 voci con categoria, catena prodotta, terminale e
imputazione) e i dati grezzi delle misure sono disponibili su richiesta: non sono
stati inclusi nel repository per non introdurre file che il progetto non ha
scelto di avere.
