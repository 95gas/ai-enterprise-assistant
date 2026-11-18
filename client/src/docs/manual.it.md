# Introduzione

Benvenuto in **ASK**, un assistente intelligente sviluppato dal Gruppo Carraro.

**ASK** utilizza una ricerca avanzata di documenti, permettendo risposte rapide e comprensibili, personalizzate sulle domande basate sul patrimonio informativo dell’organizzazione. La ricerca documentale rispetta la privacy e accede solo ai documenti consentiti all’utente dal gruppo.

Gli utenti possono interagire con **ASK** in linguaggio naturale, proprio come parlare con un collega.

## Glossario

**LLM (Large Language Model)**:  
Un tipo di modello di intelligenza artificiale progettato per comprendere e generare testo simile a quello umano in base agli input ricevuti. I LLM vengono addestrati su grandi quantità di dati testuali e utilizzano metodi statistici per prevedere e produrre risposte coerenti e contestualmente appropriate. Esempi includono i modelli GPT (Generative Pre-trained Transformer).

**Token**:  
Un’unità di testo usata dai modelli linguistici come elemento base di elaborazione. I token possono rappresentare parole, parti di parole, segni di punteggiatura o anche spazi, a seconda della lingua e del modello. Ad esempio, la parola “incredibile” potrebbe essere suddivisa in token come “in”, “credi”, e “bile” da alcuni modelli. Il numero di token determina spesso il costo computazionale e la lunghezza dell’output di una risposta LLM.

# Area di lavoro

## ASK

L’Area di Lavoro è progettata come hub principale per iniziare nuove chat e gestire sessioni interattive attraverso varie funzionalità.

### Chat Box

La Chat Box offre molteplici funzionalità per semplificare le sessioni di chat. Di seguito le principali funzioni, elencate da sinistra a destra:

- **Selettore Modello**: Permette all’utente di scegliere il modello LLM preferito per la chat. Ogni modello offre prestazioni e limiti di token distinti. Una volta esauriti i token allocati per il modello selezionato, il sistema passa automaticamente al prossimo modello disponibile.
- **Modalità**: Offre opzioni per la modalità chat:
    - **Chat**: Adatta per conversazioni e domande generali.
    - **Focus**: Ideale per interazioni centrate su un singolo documento.
- **Selettore Documenti**: Permette di filtrare i documenti accessibili. Di default, tutti i documenti che l’utente può visualizzare sono disponibili. La funzione di ricerca facilita la selezione rapida di qualsiasi documento o cartella.
- **Fonti**: Permette di specificare la Knowledge Base da cui attingere per rispondere:
    - **Modello**: Utilizza la Conoscenza Interna del LLM selezionato.
    - **Docs**: Incorpora contenuti dai documenti selezionati.
    - **Web**: Inoltra le ricerche sul web.

### Messaggi

Quando viene inviato un messaggio, esso appare nell’interfaccia della chat con relativi pulsanti di azione:

- **Messaggio Utente**:
    - **Copia**: Copia il messaggio dell’utente negli appunti.
    - **Modifica**: Permette di modificare il messaggio dell’utente e continuare la conversazione.

- **Messaggio Assistente**: Mostra un’animazione di caricamento durante la generazione della risposta, indicando i passaggi in corso da parte dell’assistente. Una volta completato, rimane solo la risposta finale con i pulsanti di azione:
    - **Informazioni**: Mostra dettagli sull’interazione, tra cui:
        - **Domanda**: Input dell’utente.
        - **Modalità**: Modalità chat attiva.
        - **Token usati**: Consumo di token (suddiviso tra input e output).
        - **Modello LLM**: Modello utilizzato per la generazione della risposta.
    - **Feedback**: Apre un modulo per inviare feedback agli sviluppatori.
    - **Copia**: Copia la risposta dell’assistente negli appunti.
    - **Espandi**: Rigenera la risposta dal punto attuale.
    - **Rigenera**: Riproduce nuovamente la risposta da zero.

A seconda del contenuto della risposta, potrebbero essere visualizzate delle citazioni come ID tra parentesi. Tipicamente, questi ID compaiono alla fine delle frasi, riferendosi alla fonte precisa usata. Le citazioni sono raggruppate per tipo (documento o pagina web) sotto la risposta e possono essere esplorate in modo interattivo.

## Conversazioni

La sezione Conversazioni presenta un elenco cronologico delle conversazioni chat passate, ordinato per ultima modifica.

- E' possibile creare una nuova chat decidendone il nome.
- La barra di ricerca aiuta a trovare le chat precedenti inserendo una parte del nome della chat, restituendo tutte le corrispondenze pertinenti indipendentemente dalla posizione.
- La cancellazione delle chat passate avviene cliccando sull’icona del cestino corrispondente.

## Documenti

La sezione Documenti mostra tutti i documenti caricati accessibili all’utente, in base ai gruppi di visibilità (vedi *Impostazioni > Dati Utente > Gruppi*).

- È disponibile una barra di ricerca per trovare rapidamente i documenti inserendo una parte del nome, mostrando tutte le voci corrispondenti.
- L’ispezione del documento si effettua cliccando su un documento, che ne apre una visualizzazione Markdown.

Opzioni avanzate sono disponibili in base ai permessi (vedi *Impostazioni > Dati Utente > Permessi*):
- **Carica comune**: Consente il caricamento di documenti in un’area condivisa. La visibilità è determinata dai gruppi assegnati. Solo gli utenti autorizzati a caricare documenti comuni possono eliminarli.
- **Carica privato**: Permette il caricamento di documenti ad accesso privato. Solo il caricatore può visualizzare ed eliminare questi documenti.
- **Elimina documento**: Si esegue cliccando sull’icona cestino accanto al documento desiderato.

# Informazioni

La sezione Informazioni opera come risorsa centralizzata per la documentazione essenziale.

Ogni sezione presenta un indice in alto a destra per facilitare la navigazione tra le risorse.

## Manuale

Offre una guida completa per comprendere e utilizzare le funzionalità e le caratteristiche dell’applicazione.

## Informativa Privacy

Fornisce spiegazioni approfondite sulla raccolta, l’uso e la protezione dei dati degli utenti, promuovendo trasparenza e fiducia.

## Aggiornamenti

Documenta tutti gli aggiornamenti passati, incluse nuove funzionalità, correzioni e miglioramenti, permettendo agli utenti di tracciare i cambiamenti e le evoluzioni dell’applicazione.

# Impostazioni

Le impostazioni permettono agli utenti di personalizzare l’esperienza e gestire i dati specifici dell’account.

## Tema

Propone opzioni per personalizzare l’aspetto visivo, come il passaggio tra modalità chiara e scura.

## Lingua

Selezione della lingua dell’interfaccia dell’applicazione. Tale modifica è puramente visiva e non influenza gli aspetti funzionali.

## Dati Utente

La sezione Dati Utente mostra informazioni dettagliate sull’account attualmente autenticato, inclusi:

- **E-mail**: Mostra l’e-mail associata all’account autenticato.
- **Nome**: Visualizza il nome del titolare dell’account.
- **Permessi**: Elenca i permessi disponibili, con spunte che indicano l’accesso garantito.
- **Gruppi**: Mostra i gruppi di visibilità supportati, evidenziando quelli accessibili. I gruppi di visibilità regolano l’accesso a determinati documenti, cartelle e funzionalità.
- **Dominio**: Indica il dominio dell’account.
- **Limite totale di token**: Indica il limite giornaliero di token (ulteriori dettagli in *Consumo Token > Utilizzo token account*).
- **Periodo di reset totale dei token**: Delinea l’intervallo per il reset del limite di token (vedi *Consumo Token > Utilizzo token account*).
- **Data di scadenza della prova**: Segna la scadenza della prova dell’account, dopo la quale l’accesso viene disabilitato.

## Consumo Token

Il Consumo Token fornisce dati sui limiti di utilizzo dell’account e metriche correlate:

- **Utilizzo token account**: Presenta il limite totale giornaliero di token.
- **Utilizzo token modelli**: Mostra i limiti di utilizzo per singolo modello, inclusi:
	- **Modello**: Nome del modello presentato all’utente.
	- **Provider**: Nome del fornitore di LLM.
    - **Periodo di reset token**: Intervallo di reset per l’utilizzo token del modello specifico.
    - **Prossimo reset**: Data e ora del prossimo reset modello.
    - **Utilizzo token**: Stato attuale del consumo token per modello.

## Disconnetti

Disconnessione dall’account autenticato.