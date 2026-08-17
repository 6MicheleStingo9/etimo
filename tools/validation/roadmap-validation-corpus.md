# Roadmap di implementazione per la validazione del corpus italiano

Questo documento raccoglie la roadmap tecnica e operativa per completare il sistema di validazione del corpus italiano di Wikizionario e trasformare il workflow attuale da "framework di validazione robusto" a "sistema di copertura reale e governato".

## 1. Definire il corpus di riferimento come snapshot immutabile

Obiettivo: stabilire un universo canonico di lemmi italiani da validare, identificato da uno snapshot preciso.

Da fare:
- scegliere la sorgente ufficiale di riferimento (dump Wikizionario italiano o API con snapshot semplificato);
- definire un identificatore di snapshot (`snapshot_id`) stabile e immutabile;
- documentare esattamente le regole di inclusione ed esclusione;
- salvare il corpus in un JSON canonico con metadata di provenance;
- garantire che la validazione utilizzi sempre il corpus dello snapshot corrente, non un insieme casuale o in evoluzione.

Criteri chiave:
- escludere acronimi e abbreviazioni;
- escludere forme flesse ovvie;
- escludere duplicati normalizzati;
- mantenere le voci target come lemmi riconoscibili e gestiti da etimo.

## 2. Rendere il corpus di riferimento versionato e verificabile

Obiettivo: avere un dataset con tracciabilità e hash di provenance.

Da fare:
- aggiungere hash del corpus e metadata di sorgente;
- registrare data di snapshot, source URL e versione del builder;
- far sì che i run di validazione possano distinguere tra "snapshot vecchio" e "snapshot nuovo";
- consentire il confronto tra snapshot per rilevare source churn e copertura evolutiva.

## 3. Completare la governance del backlog a scala reale

Obiettivo: garantire che la coda non sia solo una coda di casi, ma una coda di copertura.

Da fare:
- definire una separazione chiara tra:
  - pending
  - priority
  - retry
  - manual_review
  - pass
  - archived
  - blocked
- introdurre una politica di avanzamento su base reale:
  - nuove voci
  - casi failed da rieseguire
  - casi ambigui da review manuale
  - casi stabili da ri-controllare a TTL
- misurare il backlog age in modo automatico su ciascun elemento.

## 4. Rafforzare il tracking di source drift e parser regression

Obiettivo: rendere le diagnosi davvero affidabili.

Da fare:
- memorizzare il `source_hash` per la pagina raw del lemma validato;
- confrontare hash tra run successivi;
- classificare i fail con logica esplicita:
  - hash invariato + fail = parser regression
  - hash cambiato + fail = source drift
  - fail senza cambiamento di sorgente ma senza regressione evidente = review manuale
- esportare dati aggregati per trend di regressione e churn.

## 5. Completare le metriche di coverage e reportistica

Obiettivo: trasformare i report da semplici riepiloghi di batch a dashboard di copertura sistematica.

Da fare:
- copertura % contro il totale del corpus;
- backlog age medio e massimo;
- distribuzione dei fail per classe;
- distribuzione per categoria e tipo di lemma;
- confronto tra snapshot e trend nel tempo;
- alert su regressioni ripetute o source drift elevato.

Output attesi:
- summary Markdown per CI;
- JSON con metriche di coverage e trend;
- sezione dedicata a backlog age e source drift.

## 6. Convalidare il corpus con una vera strategia di campionamento

Obiettivo: evitare di validare solo voci “facili” o già familiari.

Da fare:
- prevedere campionamento stratificato per categoria e etimologia;
- includere casi di difficoltà crescente;
- lasciare spazio a voci ambigue, composti, mutuate, multi-step, manual_review;
- applicare una coda di priorità di tipo coverage, non solo di tipo urgency.

## 7. Rendere l’automazione GitHub Action production-grade

Obiettivo: far sì che il sistema sia affidabile in ambiente CI.

Da fare:
- gestire correttamente snapshot e artifact persistenti;
- evitare commit loop o push in condizioni non sicure;
- separare i run di validazione dai run di aggiornamento del corpus;
- registrare summary finali e dati di trend ottenuti nel tempo;
- supportare run manuali con parametri specifici di batch e di origine del corpus.

## 8. Preparare la fase di scalata a corpus massivo

Obiettivo: andare oltre il batch di 100 e costruire una copertura reale nel tempo.

Da fare:
- passare da seed e campione iniziale a corpus largamente popolato;
- incrementare il batch giornaliero in modo controllato;
- monitorare la distribuzione di pass/fail nel tempo;
- prevenire bottleneck di backlog e crescita di casi ambigui;
- definire una soglia di accettazione per l’avanzamento del corpus.

## 9. Definire il criterio di “copertura sufficiente”

Obiettivo: stabilire quando il corpus italiano è considerato sufficientemente validato per l’uso pratico.

Da fare:
- definire una soglia di copertura desiderata;
- decidere se la metrica è percentuale sul corpus totale o per categoria;
- definire la politica per lemmi ancora in manual review;
- specificare quanto tempo un lemma può restare in backlog senza essere ripreso.

## 10. Passo finale: validazione di produzione

Obiettivo: trasformare il workflow in uno strumento di qualità continua del progetto.

Da fare:
- esecuzione giornaliera automatica;
- storage di snapshot e report nel tempo;
- monitoraggio di regressioni in modo automatico;
- alerting quando il numero di source drift o parser regression aumenta;
- documentazione delle decisioni di triage e del workflow di manutenzione.

## Riassunto pratico

La situazione attuale è già molto forte come infrastruttura di validazione: coda, report, workflow, diagnostica e builder di corpus sono stati costruiti. Il rischio principale non è più il framework, ma la mancanza di un corpus di riferimento canonico, immutabile e veramente completo.

La prossima vera fase è quindi:
1. snapshot corpus reale;
2. governance di backlog e copertura;
3. metriche di drift/regressione;
4. automazione robusta e scala reale.

## Obiettivo da raggiungere

Arrivare a un sistema in cui, per ogni lemma italiano target del corpus, si sappia con certezza:
- se è stato validato;
- se è in backlog;
- se è in review manuale;
- se un fail è dovuto a regressione del parser o a cambiamento upstream di Wikizionario;
- qual è la percentuale di copertura reale del corpus nel tempo.
