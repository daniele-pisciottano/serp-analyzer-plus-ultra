# SERP Analyzer Plus Ultra

Un'applicazione web avanzata per l'analisi delle SERP (Search Engine Results Pages) con funzionalità di AI Overview analysis, tracking del proprio sito e analisi dei dati strutturati.

## Funzionalità Principali

### 🔍 Analisi SERP Completa
- **Analisi multi-keyword**: Processa fino a 100 keyword contemporaneamente
- **Classificazione automatica**: Identifica tipologie di pagine (Homepage, Blog, Prodotto, ecc.)
- **Competitor analysis**: Traccia domini e frequenza di apparizione
- **People Also Ask & Related Searches**: Estrae domande correlate e ricerche suggerite

### 🤖 AI Overview Analysis
- **Rilevamento AI Overview**: Identifica quando Google mostra AI Overview per le keyword
- **Analisi contenuto**: Utilizza GPT-4 per analizzare perché certe pagine appaiono in AI Overview
- **Suggerimenti ottimizzazione**: Fornisce raccomandazioni concrete per migliorare il posizionamento
- **Tracking fonti**: Monitora quali domini vengono citati più frequentemente

### 🏠 Site Tracking
- **Monitoraggio presenza**: Traccia il proprio sito nelle SERP e AI Overview
- **Posizioni dettagliate**: Mostra posizioni esatte e URL specifici
- **Analisi comparativa**: Confronta presenza in SERP tradizionali vs AI Overview

### 📊 Structured Data Analysis
- **Estrazione automatica**: Rileva JSON-LD, microdata e meta tags
- **Schema.org analysis**: Identifica i tipi di schema più utilizzati dai competitor
- **Best practices**: Mostra quali dati strutturati utilizzano i siti meglio posizionati

### 🧠 Semantic Clustering
- **Clustering automatico**: Raggruppa keyword per affinità semantica
- **Cluster personalizzati**: Possibilità di definire cluster basati sulla struttura del proprio sito
- **Priorità intelligente**: Assegna keyword ai cluster personalizzati quando semanticamente correlate

### 📈 Report Excel Avanzati
- **Formattazione professionale**: Font Work Sans, colori personalizzati, text wrapping automatico
- **Grafici integrati**: Visualizzazioni immediate dei dati principali
- **Tab riassuntivo**: Vista unificata di tutte le analisi per keyword
- **Esportazione completa**: Tutti i dati in formato Excel strutturato

## Requisiti

### API Keys Necessarie
- **SERPApi**: Per l'accesso ai dati delle SERP Google
- **OpenAI**: Per le analisi AI avanzate (GPT-4 raccomandato)

### Dipendenze Python
```
streamlit>=1.28.0
requests>=2.31.0
pandas>=2.0.0
openai>=1.0.0
plotly>=5.15.0
xlsxwriter>=3.1.0
urllib3>=1.26.0
aiohttp>=3.8.0
beautifulsoup4>=4.12.0
extruct>=0.13.0
```

## Installazione

1. **Clona il repository**
```bash
git clone https://github.com/your-username/serp-analyzer-plus-ultra.git
cd serp-analyzer-plus-ultra
```

2. **Installa le dipendenze**
```bash
pip install -r requirements.txt
```

3. **Ottieni le API Keys**
   - Registrati su [SERPApi](https://serpapi.com) per ottenere una chiave API
   - Ottieni una chiave API da [OpenAI](https://platform.openai.com)

4. **Avvia l'applicazione**
```bash
streamlit run app.py
```

## Utilizzo

### Configurazione Base
1. Inserisci le tue API keys nella sidebar
2. Seleziona paese e lingua per la ricerca
3. Configura il numero di risultati da analizzare (5-20)

### Tracking del Proprio Sito (Opzionale)
1. Inserisci il dominio del tuo sito nella sezione "Tracking Proprio Sito"
2. Il sistema monitorerà automaticamente la presenza nelle SERP e AI Overview

### Cluster Personalizzati (Opzionale)
1. Abilita "Clustering semantico keyword"
2. Inserisci i nomi delle pagine principali del tuo sito:
```
Servizi SEO
Corsi Online
Consulenza Marketing
Blog Aziendale
Chi Siamo
```

### Analisi Avanzate
- **Analizza pagine in AI Overview**: Analisi AI del contenuto delle pagine in AI Overview
- **Analizza dati strutturati**: Estrazione schema markup dalle prime posizioni SERP
- **Pagine da analizzare**: Configura quante pagine analizzare per query (3-10)

### Inserimento Keywords
1. Inserisci le keyword nell'area di testo (una per riga)
2. Massimo 100 keyword per analisi avanzata
3. Clicca "Avvia Analisi Avanzata"

## Output e Report

### Visualizzazioni Web
- **Metriche in tempo reale**: Dashboard con KPI principali
- **Grafici interattivi**: Plotly charts per domini, tipologie, AI Overview
- **Tabelle dettagliate**: Dati completi organizzati in tab separati

### Report Excel
Il file Excel generato include:

1. **Analisi Keyword**: Vista unificata con tutte le informazioni per keyword
2. **Top Domains**: Domini più presenti con grafico a colonne
3. **Competitor e Tipologie**: Analisi tipologie pagine con grafico a barre
4. **AI Overview**: Dettagli AI Overview per query
5. **Tracking Proprio Sito**: Performance del proprio dominio
6. **Analisi AI Overview Pages**: Insights AI sulle pagine in AI Overview
7. **Dati Strutturati SERP**: Schema markup dei competitor
8. **Keyword Clustering**: Raggruppamenti semantici

### Formattazione Excel
- **Font**: Work Sans su tutto il documento
- **Colori**: Header rosso (#E52217) con testo bianco
- **Layout**: Colonne auto-dimensionate, text wrapping, freeze panes
- **Grafici**: Integrati nei tab principali con formattazione coerente

## Architettura Tecnica

### Componenti Principali
- **EnhancedSERPAnalyzer**: Classe principale per analisi SERP
- **Session State Management**: Persistenza dati per UX migliorata
- **Modular Functions**: Separazione analisi/visualizzazione
- **Advanced Excel Formatting**: Formattazione professionale automatica

### Flusso di Elaborazione
1. **Fetch SERP Data**: Chiamate API SERPApi per ogni keyword
2. **Content Scraping**: Download e parsing delle pagine web
3. **AI Analysis**: Analisi GPT-4 del contenuto delle pagine
4. **Structured Data Extraction**: Parsing JSON-LD, microdata, meta tags
5. **Data Aggregation**: Aggregazione e correlazione dei dati
6. **Report Generation**: Creazione file Excel con grafici

### Rate Limiting
- **SERPApi**: 1 secondo tra le chiamate
- **Web Scraping**: Timeout 10 secondi per pagina
- **OpenAI**: Batch processing per ottimizzare i costi

## Limitazioni

- **Keywords**: Massimo 100 keyword per sessione (analisi avanzata)
- **Pagine**: Massimo 10 pagine analizzate per query (dati strutturati)
- **AI Overview**: Massimo 3 pagine analizzate per AI Overview per query
- **Rate Limits**: Rispetta i limiti delle API utilizzate

## Costi Stimati

### SERPApi
- ~$0.01 per query SERP
- 100 keyword = ~$1.00

### OpenAI (GPT-4)
- Clustering: ~$0.02-0.05 per 50 keyword
- AI Overview Analysis: ~$0.10-0.20 per pagina analizzata
- 100 keyword con analisi completa: ~$5-15

## Risoluzione Problemi

### Errori Comuni
- **"API Key non valida"**: Verifica le chiavi API nelle impostazioni
- **"Timeout errore"**: Riduci il numero di keyword o pagine da analizzare
- **"Quota exceeded"**: Controlla i limiti del tuo piano API

### Performance
- **Analisi lenta**: Disabilita analisi AI per velocizzare
- **Excel grande**: Riduci il numero di keyword o analisi opzionali
- **Memoria insufficiente**: Riavvia l'applicazione tra sessioni intensive


---

**Sviluppato con ❤️ da Daniele e dal suo amico Claude 🤖**
