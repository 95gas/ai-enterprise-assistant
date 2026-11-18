# Aggiornamenti - Registro delle modifiche

---

## [2.0.1] - 07-05-2026
### Aggiunte
- **Spazi privati:** Ogni utente può ora gestire fino a 10 documenti privati, offrendo maggiore flessibilità e sicurezza per informazioni personali o sensibili.
- **Integrazione con il versionamento SharePoint:** È stato implementato il versionamento dei documenti per il sito SharePoint *PROCEDURES*, in particolare all’interno della cartella *PROCEDURES*. Questo garantisce una base di conoscenza comune, solida e verificabile per tutti gli utenti.
- **Metadati dei documenti migliorati:** Nella lista dei documenti sono ora visibili metadati aggiuntivi, tra cui:
  - Data e ora di caricamento
  - Numero di token del documento
  - Dove disponibile (Wiki e SharePoint), un pulsante con collegamento diretto al documento originale
- **Nidificazione dei documenti e navigazione tra cartelle:** I documenti sono ora organizzati in cartelle annidate, rendendo più semplice strutturare le informazioni e navigare raccolte di grandi dimensioni.
- **Filtro per cartella nella chat:** Gli utenti possono filtrare gruppi di documenti in chat semplicemente selezionando una cartella; ad esempio, selezionando "WikiCarraro" per includere tutti i documenti Wiki nella base di conoscenza della sessione di chat.

### Modifiche
- **Gestione dei modelli:** I modelli legacy (GPT-5, mini, nano) sono stati rimossi a causa dei tempi di risposta lenti. Sono stati introdotti i modelli più efficienti gpt-5.4 e gpt-5.4-mini per migliorare prestazioni e affidabilità.
- **Gestione dei documenti:** È stata migliorata la gestione, l’archiviazione e la visualizzazione dei metadati dei documenti sul frontend, offrendo agli utenti un’esperienza di gestione più fluida e informativa.
- **Aggiornamento del manuale:** Il manuale utente è stato aggiornato per riflettere tutte le nuove funzionalità e i miglioramenti.

### Correzioni
- **Permessi:** Sono state corrette le assegnazioni dei permessi, garantendo che gli utenti precedentemente privi di un gruppo di visibilità attivo dispongano ora di accesso e visibilità appropriati all’interno della piattaforma.

---

## [2.0.0] - 01-04-2026
### Aggiunte
- Funzionalità chiave implementate:
  - **Chat agentica**: Capacità di pianificazione e ragionamento attive; ASK scompone automaticamente le richieste complesse e determina gli strumenti da utilizzare per fornire risposte complete, iterando se necessario.
  - **Ricerca Web integrata e ricerca avanzata**: Navigazione web in tempo reale e confronto incrociato di dati esterni con la knowledge base aziendale tramite filtri di ricerca avanzati.
  - **Sincronizzazione dinamica del Wiki**: Aggiorna automaticamente le informazioni tra il Wiki aziendale e la knowledge base di ASK entro 24 ore, garantendo un'unica fonte di verità.

### Modifiche
- Riprogettazione dei filtri di ricerca nell'interfaccia utente (UI) per promuovere trasparenza, fiducia e controllo.
- Introduzione di:
  - Distinzione tra le **fonti** di ciascuna risposta (web o basate su documenti).
  - Rimosso il sistema di **ruoli** a favore dei **permessi**, per visualizzare chiaramente i permessi dell'utente connesso.
- Nuove **scorciatoie**, **logo ufficiale**, manuale aggiornato e **informativa sulla privacy**.
- Transizione del backend a un'architettura **a microservizi** e **cloud-native** (integrazione con S3), migliorando scalabilità e sicurezza.
- Implementato lo **strumento di streaming** integrato con la ricerca agentica, per rendere visibili le azioni calcolate da ASK.

### Correzioni
- Gestione del contesto ottimizzata grazie alla **Cronologia chat dinamica**, che mantiene la memoria della conversazione senza sprecare risorse.
- Introduzione dei **token JWT** per un'autenticazione sicura tra server e microservizi.
- Risolti i problemi di coerenza tra gli ambienti di test e di produzione grazie alla **dockerizzazione del frontend**.