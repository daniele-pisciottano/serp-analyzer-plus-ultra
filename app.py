import streamlit as st
import requests
import pandas as pd
import time
import json
from collections import Counter, defaultdict
from urllib.parse import urlparse, urljoin
from openai import OpenAI
from io import BytesIO
import plotly.express as px
import plotly.graph_objects as go
import asyncio
import aiohttp
import concurrent.futures
import threading
from functools import lru_cache
import re
from bs4 import BeautifulSoup
import extruct
from urllib.robotparser import RobotFileParser
import random
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configurazione della pagina
st.set_page_config(
    page_title="SERP Analyzer Plus Ultra",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS personalizzato
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        text-align: center;
        color: #1f77b4;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #1f77b4;
    }
    .stProgress .st-bo {
        background-color: #1f77b4;
    }
    .ai-overview-box {
        background-color: #e8f4fd;
        border: 2px solid #1f77b4;
        border-radius: 0.5rem;
        padding: 1rem;
        margin: 1rem 0;
    }
    .own-site-highlight {
        background-color: #d4edda;
        border: 2px solid #28a745;
        border-radius: 0.5rem;
        padding: 1rem;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

# Inizializza session state per persistenza dati
if 'analysis_complete' not in st.session_state:
    st.session_state.analysis_complete = False
if 'analysis_data' not in st.session_state:
    st.session_state.analysis_data = {}

class EnhancedSERPAnalyzer:
    def __init__(self, serpapi_key, openai_api_key, own_site_domain=None):
        self.serpapi_key = serpapi_key
        self.openai_api_key = openai_api_key
        self.own_site_domain = own_site_domain
        self.serpapi_url = "https://serpapi.com/search.json"
        self.client = OpenAI(api_key=openai_api_key) if openai_api_key != "dummy" else None
        self.classification_cache = {}
        self.content_cache = {}
        self.structured_data_cache = {}
        self.use_ai = True
        self.batch_size = 5
        
        # Headers per web scraping
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        }

    def fetch_serp_results(self, query, country="it", language="it", num_results=10):
        """Effettua la ricerca SERP tramite SERPApi"""
        params = {
            "api_key": self.serpapi_key,
            "engine": "google",
            "q": query,
            "num": num_results,
            "gl": country,
            "hl": language,
            "google_domain": "google.it" if country == "it" else "google.com"
        }
        
        try:
            response = requests.get(self.serpapi_url, params=params)
            if response.status_code == 200:
                return response.json()
            else:
                st.error(f"Errore SERPApi per query '{query}': {response.status_code}")
                return None
        except Exception as e:
            st.error(f"Errore di connessione: {e}")
            return None

    def fetch_page_content(self, url, timeout=10):
        """Fetcha il contenuto di una pagina web"""
        if url in self.content_cache:
            return self.content_cache[url]
        
        try:
            response = requests.get(url, headers=self.headers, timeout=timeout)
            if response.status_code == 200:
                content = {
                    'url': url,
                    'html': response.text,
                    'status_code': response.status_code,
                    'headers': dict(response.headers)
                }
                self.content_cache[url] = content
                return content
            else:
                return {'url': url, 'html': '', 'status_code': response.status_code, 'error': f'HTTP {response.status_code}'}
        except requests.RequestException as e:
            return {'url': url, 'html': '', 'status_code': 0, 'error': str(e)}

    def extract_structured_data(self, html_content, url):
        """Estrae dati strutturati da una pagina HTML"""
        if url in self.structured_data_cache:
            return self.structured_data_cache[url]
        
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            structured_data = {
                'json_ld': [],
                'microdata': [],
                'rdfa': [],
                'meta_tags': {},
                'schema_types': set()
            }
            
            # Estrai JSON-LD
            json_scripts = soup.find_all('script', type='application/ld+json')
            for script in json_scripts:
                try:
                    data = json.loads(script.string)
                    structured_data['json_ld'].append(data)
                    # Estrai tipi di schema
                    if isinstance(data, dict) and '@type' in data:
                        structured_data['schema_types'].add(data['@type'])
                    elif isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict) and '@type' in item:
                                structured_data['schema_types'].add(item['@type'])
                except json.JSONDecodeError:
                    continue
            
            # Estrai meta tags importanti
            meta_tags = soup.find_all('meta')
            for meta in meta_tags:
                if meta.get('property'):
                    structured_data['meta_tags'][meta.get('property')] = meta.get('content', '')
                elif meta.get('name'):
                    structured_data['meta_tags'][meta.get('name')] = meta.get('content', '')
            
            # Estrai microdata e RDFa usando extruct (se possibile)
            try:
                extracted = extruct.extract(html_content, url)
                structured_data['microdata'] = extracted.get('microdata', [])
                structured_data['rdfa'] = extracted.get('rdfa', [])
                
                # Aggiungi tipi schema da microdata
                for item in structured_data['microdata']:
                    if 'type' in item:
                        structured_data['schema_types'].add(item['type'].split('/')[-1])
                        
            except Exception:
                pass  # extruct potrebbe non essere disponibile
            
            # Converti set in lista per serializzazione
            structured_data['schema_types'] = list(structured_data['schema_types'])
            
            self.structured_data_cache[url] = structured_data
            return structured_data
            
        except Exception as e:
            return {'error': str(e), 'json_ld': [], 'microdata': [], 'rdfa': [], 'meta_tags': {}, 'schema_types': []}

    def analyze_page_content_for_ai_overview(self, url, query, page_content):
        """Analizza il contenuto di una pagina per capire perché è in AI Overview"""
        if not self.client:
            return "Analisi AI non disponibile"
        
        try:
            soup = BeautifulSoup(page_content, 'html.parser')
            
            # Estrai testo principale
            for script in soup(["script", "style"]):
                script.decompose()
            
            text_content = soup.get_text()
            # Limita il contenuto per evitare token limits
            text_content = text_content[:4000]
            
            # Estrai headings
            headings = []
            for i in range(1, 7):
                for heading in soup.find_all(f'h{i}'):
                    headings.append(f"H{i}: {heading.get_text().strip()}")
            
            # Estrai informazioni su immagini
            images = soup.find_all('img')
            image_info = []
            for img in images[:5]:  # Prime 5 immagini
                alt_text = img.get('alt', 'No alt text')
                src = img.get('src', 'No src')
                image_info.append(f"Immagine: {alt_text} (src: {src})")
            
            # Estrai link
            links = soup.find_all('a', href=True)
            internal_links = len([link for link in links if urlparse(url).netloc in link.get('href', '')])
            external_links = len(links) - internal_links
            
            prompt = f"""Analizza questa pagina che appare in AI Overview per la query "{query}" e fornisci insights sul perché potrebbe essere ben posizionata.

URL: {url}

HEADINGS:
{chr(10).join(headings[:10])}

CONTENUTO (primi 4000 caratteri):
{text_content}

ELEMENTI MULTIMEDIALI:
{chr(10).join(image_info)}

STRUTTURA LINK:
- Link interni: {internal_links}
- Link esterni: {external_links}

Fornisci un'analisi strutturata su:
1. RILEVANZA CONTENUTO: Perché questo contenuto risponde bene alla query
2. QUALITÀ TECNICA: Aspetti tecnici che favoriscono il posizionamento  
3. STRUTTURA: Come è organizzato il contenuto
4. ELEMENTI MULTIMEDIALI: Uso di immagini, video, etc.
5. AUTOREVOLEZZA: Segnali di autorità e affidabilità
6. SUGGERIMENTI: 3 azioni concrete per ottimizzare una pagina simile

Mantieni l'analisi concisa ma dettagliata (max 500 parole)."""

            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=800,
                temperature=0.3
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            return f"Errore nell'analisi AI: {str(e)}"

    @lru_cache(maxsize=1000)
    def classify_page_type_rule_based(self, url, title, snippet=""):
        """Classificazione veloce basata su regole per casi comuni"""
        url_lower = url.lower()
        title_lower = title.lower()
        snippet_lower = snippet.lower()
        
        # Homepage patterns
        if (url_lower.count('/') <= 3 and 
            ('home' in url_lower or url_lower.endswith('.com') or url_lower.endswith('.it') or
             'homepage' in title_lower or 'home page' in title_lower)):
            return "Homepage"
        
        # Product page patterns
        product_patterns = ['product', 'prodotto', 'item', 'articolo', '/p/', 'buy', 'acquista', 'shop']
        if any(pattern in url_lower for pattern in product_patterns):
            return "Pagina Prodotto"
        
        # Category page patterns  
        category_patterns = ['category', 'categoria', 'catalogo', 'catalog', 'collection', 'collezione', 'products', 'prodotti']
        if any(pattern in url_lower for pattern in category_patterns):
            return "Pagina di Categoria"
            
        # Blog patterns
        blog_patterns = ['blog', 'news', 'notizie', 'articolo', 'post', 'article', '/blog/', 'magazine']
        if any(pattern in url_lower for pattern in blog_patterns):
            return "Articolo di Blog"
            
        # Services patterns
        service_patterns = ['service', 'servizio', 'servizi', 'services', 'consulenza', 'consulting']
        if any(pattern in url_lower for pattern in service_patterns):
            return "Pagina di Servizi"
            
        return None

    def classify_page_type_gpt(self, url, title, snippet=""):
        """Classificazione con OpenAI solo per casi complessi"""
        # Prima prova la classificazione rule-based
        rule_based_result = self.classify_page_type_rule_based(url, title, snippet)
        if rule_based_result:
            return rule_based_result
            
        # Cache check
        cache_key = f"{url}_{title}"
        if cache_key in self.classification_cache:
            return self.classification_cache[cache_key]
        
        # Prompt ottimizzato per velocità
        prompt = f"""Classifica SOLO con una di queste categorie:
        
URL: {url}
Titolo: {title}

Categorie: Homepage, Pagina di Categoria, Pagina Prodotto, Articolo di Blog, Pagina di Servizi, Altro

Rispondi solo con la categoria."""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "user", "content": prompt}
                ],
                max_tokens=10,
                temperature=0
            )
            result = response.choices[0].message.content.strip()
            self.classification_cache[cache_key] = result
            return result
        except Exception as e:
            st.warning(f"Errore OpenAI: {e}")
            return "Altro"

    def parse_ai_overview(self, data):
        """Estrae informazioni dall'AI Overview secondo la documentazione SERPApi"""
        ai_overview_info = {
            "has_ai_overview": False,
            "ai_overview_text": "",
            "ai_sources": [],
            "ai_source_domains": [],
            "page_token": None,
            "own_site_in_ai": False,
            "own_site_ai_position": None
        }
        
        # Controlla se c'è AI Overview embedded nei risultati
        if "ai_overview" in data:
            ai_data = data["ai_overview"]
            ai_overview_info["has_ai_overview"] = True
            
            # Estrai testo dai text_blocks
            if "text_blocks" in ai_data:
                text_parts = []
                for block in ai_data["text_blocks"]:
                    if "snippet" in block:
                        text_parts.append(block["snippet"])
                    
                    # Se è una lista, estrai anche gli elementi
                    if block.get("type") == "list" and "list" in block:
                        for item in block["list"]:
                            if "title" in item:
                                text_parts.append(f"• {item['title']}")
                            if "snippet" in item:
                                text_parts.append(f"  {item['snippet']}")
                
                ai_overview_info["ai_overview_text"] = " ".join(text_parts)
            
            # Estrai references (fonti) e controlla il proprio sito
            if "references" in ai_data:
                for i, ref in enumerate(ai_data["references"]):
                    source_info = {
                        "title": ref.get("title", ""),
                        "link": ref.get("link", ""),
                        "domain": urlparse(ref.get("link", "")).netloc if ref.get("link") else "",
                        "source": ref.get("source", ""),
                        "snippet": ref.get("snippet", ""),
                        "position": i + 1
                    }
                    ai_overview_info["ai_sources"].append(source_info)
                    if source_info["domain"]:
                        ai_overview_info["ai_source_domains"].append(source_info["domain"])
                    
                    # Controlla se il proprio sito è presente
                    if self.own_site_domain and self.own_site_domain in source_info["domain"]:
                        ai_overview_info["own_site_in_ai"] = True
                        if ai_overview_info["own_site_ai_position"] is None:
                            ai_overview_info["own_site_ai_position"] = i + 1
        
        # Fallback: cerca in answer_box come AI Overview alternativo
        if not ai_overview_info["has_ai_overview"] and "answer_box" in data:
            answer_box = data["answer_box"]
            if isinstance(answer_box, dict):
                ai_overview_info["has_ai_overview"] = True
                ai_overview_info["ai_overview_text"] = str(answer_box.get("snippet", answer_box.get("answer", "")))
                
                if "link" in answer_box:
                    source_info = {
                        "title": answer_box.get("title", ""),
                        "link": answer_box.get("link", ""),
                        "domain": urlparse(answer_box.get("link", "")).netloc if answer_box.get("link") else "",
                        "position": 1
                    }
                    ai_overview_info["ai_sources"].append(source_info)
                    if source_info["domain"]:
                        ai_overview_info["ai_source_domains"].append(source_info["domain"])
                    
                    # Controlla il proprio sito
                    if self.own_site_domain and self.own_site_domain in source_info["domain"]:
                        ai_overview_info["own_site_in_ai"] = True
                        ai_overview_info["own_site_ai_position"] = 1
        
        return ai_overview_info

    def analyze_ai_overview_pages(self, ai_overview_info, query):
        """Analizza le pagine presenti in AI Overview"""
        ai_analysis_results = []
        
        if not ai_overview_info["ai_sources"]:
            return ai_analysis_results
        
        # Analizza massimo 3 pagine per evitare tempi troppo lunghi
        sources_to_analyze = ai_overview_info["ai_sources"][:3]
        
        for source in sources_to_analyze:
            if not source["link"]:
                continue
                
            # Fetch contenuto della pagina
            content_data = self.fetch_page_content(source["link"])
            
            if content_data.get("html"):
                # Analizza contenuto con AI
                ai_analysis = self.analyze_page_content_for_ai_overview(
                    source["link"], 
                    query, 
                    content_data["html"]
                )
                
                # Estrai dati strutturati
                structured_data = self.extract_structured_data(content_data["html"], source["link"])
                
                ai_analysis_results.append({
                    "query": query,
                    "url": source["link"],
                    "title": source["title"],
                    "domain": source["domain"],
                    "position_in_ai": source["position"],
                    "ai_analysis": ai_analysis,
                    "schema_types": ", ".join(structured_data["schema_types"]),
                    "has_json_ld": len(structured_data["json_ld"]) > 0,
                    "meta_tags_count": len(structured_data["meta_tags"])
                })
            else:
                ai_analysis_results.append({
                    "query": query,
                    "url": source["link"],
                    "title": source["title"],
                    "domain": source["domain"],
                    "position_in_ai": source["position"],
                    "ai_analysis": f"Errore nel recupero contenuto: {content_data.get('error', 'Sconosciuto')}",
                    "schema_types": "",
                    "has_json_ld": False,
                    "meta_tags_count": 0
                })
        
        return ai_analysis_results

    def analyze_top_serp_structured_data(self, organic_results, query, max_pages=5):
        """Analizza i dati strutturati delle prime pagine SERP"""
        structured_data_results = []
        
        for i, result in enumerate(organic_results[:max_pages]):
            url = result.get("link", "")
            if not url:
                continue
            
            # Fetch contenuto
            content_data = self.fetch_page_content(url)
            
            if content_data.get("html"):
                # Estrai dati strutturati
                structured_data = self.extract_structured_data(content_data["html"], url)
                
                structured_data_results.append({
                    "query": query,
                    "serp_position": i + 1,
                    "url": url,
                    "title": result.get("title", ""),
                    "domain": urlparse(url).netloc,
                    "schema_types": ", ".join(structured_data["schema_types"]),
                    "json_ld_count": len(structured_data["json_ld"]),
                    "microdata_count": len(structured_data["microdata"]),
                    "meta_tags_count": len(structured_data["meta_tags"]),
                    "has_breadcrumbs": any("breadcrumb" in str(data).lower() for data in structured_data["json_ld"]),
                    "has_faq": any("faq" in str(data).lower() for data in structured_data["json_ld"]),
                    "has_review": any("review" in str(data).lower() for data in structured_data["json_ld"])
                })
            else:
                structured_data_results.append({
                    "query": query,
                    "serp_position": i + 1,
                    "url": url,
                    "title": result.get("title", ""),
                    "domain": urlparse(url).netloc,
                    "schema_types": "",
                    "json_ld_count": 0,
                    "microdata_count": 0,
                    "meta_tags_count": 0,
                    "has_breadcrumbs": False,
                    "has_faq": False,
                    "has_review": False,
                    "error": content_data.get('error', 'Errore sconosciuto')
                })
        
        return structured_data_results

    def parse_results(self, data, query):
        """Analizza i risultati SERP con tutte le nuove funzionalità"""
        domain_page_types = defaultdict(lambda: defaultdict(int))
        domain_occurences = defaultdict(int)
        query_page_types = defaultdict(list)
        paa_questions = []
        related_queries = []
        paa_to_queries = defaultdict(set)
        related_to_queries = defaultdict(set)
        paa_to_domains = defaultdict(set)
        
        # Tracking del proprio sito
        own_site_data = {
            "in_serp": False,
            "serp_positions": [],
            "serp_urls": [],
            "total_appearances": 0
        }

        pages_to_classify = []
        pages_info = []
        
        # Analizza AI Overview con nuove funzionalità
        ai_overview_info = self.parse_ai_overview(data)
        
        # Analizza risultati organici
        organic_results = data.get("organic_results", [])
        
        for i, result in enumerate(organic_results):
            domain = urlparse(result["link"]).netloc
            url = result["link"]
            title = result.get("title", "")
            snippet = result.get("snippet", "")
            position = i + 1
            
            # Controlla se è il proprio sito
            if self.own_site_domain and self.own_site_domain in domain:
                own_site_data["in_serp"] = True
                own_site_data["serp_positions"].append(position)
                own_site_data["serp_urls"].append(url)
                own_site_data["total_appearances"] += 1
            
            page_type = self.classify_page_type_rule_based(url, title, snippet)
            
            if page_type:
                domain_page_types[domain][page_type] += 1
                domain_occurences[domain] += 1
                query_page_types[query].append(page_type)
            else:
                pages_to_classify.append((url, title, snippet))
                pages_info.append((domain, url, title, snippet))

        # Classificazione AI per pagine non classificate con regole
        if pages_to_classify and self.use_ai:
            # Implementa batch classification qui se necessario
            for domain, url, title, snippet in pages_info:
                page_type = self.classify_page_type_gpt(url, title, snippet)
                domain_page_types[domain][page_type] += 1
                domain_occurences[domain] += 1
                query_page_types[query].append(page_type)

        # Analizza People Also Ask
        if "people_also_ask" in data:
            for paa in data["people_also_ask"]:
                paa_text = paa.get("question", "")
                if paa_text:
                    paa_questions.append(paa_text)
                    paa_to_queries[paa_text].add(query)
                    paa_to_domains[paa_text].update([domain for domain in domain_page_types.keys()])

        # Analizza Related Searches
        if "related_searches" in data:
            for related in data["related_searches"]:
                related_text = related.get("query", "")
                if related_text:
                    related_queries.append(related_text)
                    related_to_queries[related_text].add(query)

        return (domain_page_types, domain_occurences, query_page_types, 
                paa_questions, related_queries, paa_to_queries, 
                related_to_queries, paa_to_domains, ai_overview_info, 
                own_site_data, organic_results)

    def cluster_keywords_with_custom(self, keywords, custom_clusters):
        """Clusterizza le keyword usando cluster personalizzati come priorità"""
        if not self.client or not self.use_ai:
            return self.cluster_keywords_simple_custom(keywords, custom_clusters)
        
        # Dividi in batch per evitare prompt troppo lunghi
        batch_size = 50
        all_clusters = {}
        
        # Inizializza cluster personalizzati
        for cluster_name in custom_clusters:
            all_clusters[cluster_name] = []
        
        for i in range(0, len(keywords), batch_size):
            batch_keywords = keywords[i:i+batch_size]
            
            prompt = f"""Ruolo: Esperto di analisi semantica e architettura siti web
Capacità: Specialista in clustering di keyword basato su strutture di siti web esistenti.

Compito: Assegna ogni keyword al cluster più appropriato, dando PRIORITÀ ai cluster predefiniti del sito.

CLUSTER PREDEFINITI (USA QUESTI COME PRIORITÀ):
{chr(10).join([f"- {cluster}" for cluster in custom_clusters])}

Keyword da classificare:
{chr(10).join([f"- {kw}" for kw in batch_keywords])}

Istruzioni:
1. PRIORITÀ ASSOLUTA: Cerca di assegnare ogni keyword a uno dei cluster predefiniti se semanticamente correlata
2. Solo se una keyword NON può essere associata a nessun cluster predefinito, crea un nuovo cluster
3. Ogni cluster deve avere almeno 3 keyword (per quelli nuovi)
4. Se una keyword non si adatta a nessun cluster, mettila in "Generale"

Formato di risposta:
Cluster: [Nome Cluster Predefinito o Nuovo]
- keyword1
- keyword2
- keyword3

Cluster: [Altro Cluster]
- keyword4
- keyword5"""

            try:
                response = self.client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=2000,
                    temperature=0.2
                )
                
                # Parse della risposta
                response_text = response.choices[0].message.content.strip()
                clusters = self.parse_clustering_response_custom(response_text, custom_clusters)
                
                # Merge dei risultati
                for cluster_name, cluster_keywords in clusters.items():
                    if cluster_name in all_clusters:
                        all_clusters[cluster_name].extend(cluster_keywords)
                    else:
                        all_clusters[cluster_name] = cluster_keywords
                
            except Exception as e:
                st.warning(f"Errore clustering personalizzato batch {i//batch_size + 1}: {e}")
                # Fallback per questo batch
                simple_clusters = self.cluster_keywords_simple_custom(batch_keywords, custom_clusters)
                for cluster_name, cluster_keywords in simple_clusters.items():
                    if cluster_name in all_clusters:
                        all_clusters[cluster_name].extend(cluster_keywords)
                    else:
                        all_clusters[cluster_name] = cluster_keywords
        
        # Pulisci cluster vuoti
        final_clusters = {k: v for k, v in all_clusters.items() if v}
        
        return final_clusters

    def cluster_keywords_simple_custom(self, keywords, custom_clusters):
        """Clustering semplice con cluster personalizzati (fallback)"""
        clusters = {}
        
        # Inizializza cluster personalizzati
        for cluster_name in custom_clusters:
            clusters[cluster_name] = []
        
        unassigned_keywords = []
        
        for keyword in keywords:
            keyword_lower = keyword.lower()
            assigned = False
            
            # Prova ad assegnare a cluster personalizzati
            for cluster_name in custom_clusters:
                cluster_words = cluster_name.lower().split()
                if any(word in keyword_lower or keyword_lower in word for word in cluster_words):
                    clusters[cluster_name].append(keyword)
                    assigned = True
                    break
            
            if not assigned:
                unassigned_keywords.append(keyword)
        
        # Raggruppa keyword non assegnate
        if unassigned_keywords:
            auto_clusters = self.cluster_keywords_simple(unassigned_keywords)
            clusters.update(auto_clusters)
        
        # Rimuovi cluster vuoti
        final_clusters = {k: v for k, v in clusters.items() if v}
        
        return final_clusters

    def parse_clustering_response_custom(self, response_text, custom_clusters):
        """Parse della risposta di clustering personalizzato"""
        clusters = {}
        current_cluster = None
        
        lines = response_text.split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('Cluster:'):
                current_cluster = line.replace('Cluster:', '').strip()
                clusters[current_cluster] = []
            elif line.startswith('-') and current_cluster:
                keyword = line.replace('-', '').strip()
                if keyword:
                    clusters[current_cluster].append(keyword)
        
        # Per cluster personalizzati, accetta anche cluster con meno di 5 keyword
        # ma per quelli nuovi mantieni il minimo
        valid_clusters = {}
        small_keywords = []
        
        for cluster_name, keywords in clusters.items():
            if cluster_name in custom_clusters:
                # Cluster personalizzati: accetta qualsiasi size
                valid_clusters[cluster_name] = keywords
            elif len(keywords) >= 3:
                # Cluster nuovi: minimo 3 keyword
                valid_clusters[cluster_name] = keywords
            else:
                small_keywords.extend(keywords)
        
        if small_keywords:
            if "Generale" in valid_clusters:
                valid_clusters["Generale"].extend(small_keywords)
            else:
                valid_clusters["Generale"] = small_keywords
        
        return valid_clusters

    def cluster_keywords_semantic(self, keywords):
        """Clusterizza le keyword per gruppi semantici usando OpenAI"""
        if not self.client or not self.use_ai:
            return self.cluster_keywords_simple(keywords)
        
        batch_size = 50
        all_clusters = {}
        
        for i in range(0, len(keywords), batch_size):
            batch_keywords = keywords[i:i+batch_size]
            
            prompt = f"""Ruolo: Esperto di analisi semantica
Capacità: Possiedi competenze approfondite in linguistica computazionale, analisi semantica e clustering di parole chiave.

Compito: Clusterizza il seguente elenco di keyword raggruppando quelle appartenenti allo stesso gruppo semantico. Ogni cluster deve contenere ALMENO 5 keyword per essere valido.

Elenco keyword da analizzare:
{chr(10).join([f"- {kw}" for kw in batch_keywords])}

Istruzioni:
1. Raggruppa le keyword per similarità semantica, significato e contesto d'uso
2. Ogni cluster deve avere almeno 5 keyword
3. Se una keyword non ha abbastanza correlate, inseriscila nel cluster "Generale"
4. Dai un nome descrittivo a ogni cluster

Formato di risposta:
Cluster: [Nome Cluster]
- keyword1
- keyword2
- keyword3
- keyword4
- keyword5

Cluster: [Nome Cluster 2]
- keyword6
- keyword7
[etc...]"""

            try:
                response = self.client.chat.completions.create(
                    model="gpt-4o",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=2000,
                    temperature=0.3
                )
                
                response_text = response.choices[0].message.content.strip()
                clusters = self.parse_clustering_response(response_text)
                all_clusters.update(clusters)
                
            except Exception as e:
                st.warning(f"Errore clustering OpenAI batch {i//batch_size + 1}: {e}")
                simple_clusters = self.cluster_keywords_simple(batch_keywords)
                all_clusters.update(simple_clusters)
        
        return all_clusters

    def cluster_keywords_simple(self, keywords):
        """Clustering semplice basato su parole comuni (fallback)"""
        clusters = defaultdict(list)
        
        for keyword in keywords:
            words = keyword.lower().split()
            main_word = words[0] if words else keyword
            
            assigned = False
            for cluster_name in clusters:
                if any(word in cluster_name.lower() or cluster_name.lower() in word for word in words):
                    clusters[cluster_name].append(keyword)
                    assigned = True
                    break
            
            if not assigned:
                clusters[f"Cluster {main_word.capitalize()}"].append(keyword)
        
        final_clusters = {}
        small_clusters = []
        
        for cluster_name, cluster_keywords in clusters.items():
            if len(cluster_keywords) >= 5:
                final_clusters[cluster_name] = cluster_keywords
            else:
                small_clusters.extend(cluster_keywords)
        
        if small_clusters:
            final_clusters["Generale"] = small_clusters
        
        return final_clusters

    def parse_clustering_response(self, response_text):
        """Parse della risposta di clustering da OpenAI"""
        clusters = {}
        current_cluster = None
        
        lines = response_text.split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('Cluster:'):
                current_cluster = line.replace('Cluster:', '').strip()
                clusters[current_cluster] = []
            elif line.startswith('-') and current_cluster:
                keyword = line.replace('-', '').strip()
                if keyword:
                    clusters[current_cluster].append(keyword)
        
        valid_clusters = {}
        small_keywords = []
        
        for cluster_name, keywords in clusters.items():
            if len(keywords) >= 5:
                valid_clusters[cluster_name] = keywords
            else:
                small_keywords.extend(keywords)
        
        if small_keywords:
            valid_clusters["Generale"] = small_keywords
        
        return valid_clusters

    def create_enhanced_excel_report(self, domains_counter, domain_occurences, query_page_types, 
                                   domain_page_types, paa_questions, related_queries, 
                                   paa_to_queries, related_to_queries, paa_to_domains, 
                                   ai_overview_data, own_site_tracking, ai_analysis_data,
                                   structured_data_analysis, keyword_clusters=None):
        """Crea il report Excel potenziato con formattazione professionale"""
        
        # DataFrames esistenti...
        domain_page_types_list = []
        page_type_counter = Counter()

        for domain, page_type_dict in domain_page_types.items():
            domain_data = {
                "Competitor": domain, 
                "Numero occorrenze": domain_occurences[domain]
            }
            
            for page_type in ['Homepage', 'Pagina di Categoria', 'Pagina Prodotto', 
                            'Articolo di Blog', 'Pagina di Servizi', 'Altro']:
                domain_data[page_type] = page_type_dict.get(page_type, 0)
                page_type_counter[page_type] += domain_data[page_type]
            
            domain_page_types_list.append(domain_data)

        domain_page_types_df = pd.DataFrame(domain_page_types_list)
        
        # ORDINAMENTO DECRESCENTE per occorrenze
        domains_df = pd.DataFrame(domains_counter.items(), columns=["Dominio", "Occorrenze"])
        domains_df = domains_df.sort_values("Occorrenze", ascending=False).reset_index(drop=True)
        total_queries = sum(domains_counter.values())
        domains_df["% Presenza"] = (domains_df["Occorrenze"] / total_queries * 100).round(2)
        
        # Ordina anche competitor e tipologie per occorrenze
        domain_page_types_df = domain_page_types_df.sort_values("Numero occorrenze", ascending=False).reset_index(drop=True)

        # Tracking del proprio sito
        own_site_df = pd.DataFrame()
        if own_site_tracking:
            own_site_data = []
            for query, site_data in own_site_tracking.items():
                if site_data["in_serp"] or site_data.get("in_ai_overview"):
                    own_site_data.append({
                        "Query": query,
                        "In SERP": site_data["in_serp"],
                        "Posizioni SERP": ", ".join(map(str, site_data["serp_positions"])) if site_data["serp_positions"] else "",
                        "In AI Overview": site_data.get("in_ai_overview", False),
                        "Posizione AI Overview": site_data.get("ai_overview_position", ""),
                        "URLs SERP": "; ".join(site_data["serp_urls"]) if site_data["serp_urls"] else ""
                    })
            own_site_df = pd.DataFrame(own_site_data)

        # Analisi AI Overview delle pagine
        ai_analysis_df = pd.DataFrame(ai_analysis_data)

        # Analisi dati strutturati
        structured_data_df = pd.DataFrame(structured_data_analysis)

        # NUOVO: Creazione del tab "Analisi Keyword" riassuntivo
        keyword_analysis_data = []
        all_queries = list(ai_overview_data.keys())
        
        for query in all_queries:
            # Trova il cluster di appartenenza
            cluster_name = "Non clusterizzato"
            if keyword_clusters:
                for cluster, keywords in keyword_clusters.items():
                    if query in keywords:
                        cluster_name = cluster
                        break
            
            # Info AI Overview
            ai_info = ai_overview_data.get(query, {})
            has_ai_overview = ai_info.get("has_ai_overview", False)
            num_sources = len(ai_info.get("ai_sources", []))
            my_site_in_ai = ai_info.get("own_site_in_ai", False)
            
            # Analisi AI Overview (testo completo - non troncato)
            ai_analysis_text = ""
            for ai_item in ai_analysis_data:
                if ai_item["query"] == query:
                    ai_analysis_text = ai_item["ai_analysis"]  # Testo completo
                    break
            
            # Dati strutturati (schema types più comuni per questa query)
            schema_types_list = []
            for struct_item in structured_data_analysis:
                if struct_item["query"] == query and struct_item.get("schema_types"):
                    schema_types_list.extend([s.strip() for s in struct_item["schema_types"].split(',')])
            
            most_common_schemas = ", ".join([schema for schema, count in Counter(schema_types_list).most_common(3)])
            
            # Tipologia di pagina più frequente per questa query
            page_types_for_query = query_page_types.get(query, [])
            most_common_page_type = Counter(page_types_for_query).most_common(1)
            most_common_page_type = most_common_page_type[0][0] if most_common_page_type else "N/A"
            
            keyword_analysis_data.append({
                "Keyword": query,
                "Cluster di riferimento": cluster_name,
                "AI Overview": "SI" if has_ai_overview else "NO",
                "Numero fonti": num_sources,
                "Il mio sito compare": "SI" if my_site_in_ai else "NO",
                "Dati strutturati SERP": most_common_schemas,
                "Analisi AI Overview": ai_analysis_text if ai_analysis_text else "N/A",
                "Tipologia risultato": most_common_page_type
            })
        
        keyword_analysis_df = pd.DataFrame(keyword_analysis_data)

        # Altri DataFrames per AI Overview
        ai_overview_list = []
        ai_sources_list = []
        
        for query, ai_info in ai_overview_data.items():
            ai_overview_list.append({
                "Query": query,
                "Ha AI Overview": ai_info["has_ai_overview"],
                "Testo AI Overview": ai_info["ai_overview_text"],  # Testo completo
                "Numero Fonti": len(ai_info["ai_sources"]),
                "Proprio Sito in AI": ai_info.get("own_site_in_ai", False),
                "Posizione Proprio Sito": ai_info.get("own_site_ai_position", "")
            })
            
            for i, source in enumerate(ai_info["ai_sources"]):
                ai_sources_list.append({
                    "Query": query,
                    "Fonte #": i + 1,
                    "Titolo Fonte": source["title"],
                    "Link Fonte": source["link"],
                    "Dominio Fonte": source["domain"]
                })
        
        ai_overview_df = pd.DataFrame(ai_overview_list)
        ai_sources_df = pd.DataFrame(ai_sources_list)

        # Salva tutto in Excel con formattazione professionale
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            workbook = writer.book
            
            # Definisci formati personalizzati con Work Sans e colore richiesto
            header_format = workbook.add_format({
                'bold': True,
                'bg_color': '#E52217',
                'font_color': 'white',
                'border': 1,
                'align': 'center',
                'valign': 'vcenter',
                'text_wrap': True,
                'font_name': 'Work Sans',
                'font_size': 11
            })
            
            cell_format = workbook.add_format({
                'border': 1,
                'text_wrap': True,
                'valign': 'top',
                'font_name': 'Work Sans',
                'font_size': 10
            })
            
            cell_center_format = workbook.add_format({
                'border': 1,
                'align': 'center',
                'valign': 'vcenter',
                'font_name': 'Work Sans',
                'font_size': 10
            })
            
            number_format = workbook.add_format({
                'border': 1,
                'num_format': '#,##0',
                'align': 'center',
                'valign': 'vcenter',
                'font_name': 'Work Sans',
                'font_size': 10
            })
            
            percentage_format = workbook.add_format({
                'border': 1,
                'num_format': '0.00%',
                'align': 'center',
                'valign': 'vcenter',
                'font_name': 'Work Sans',
                'font_size': 10
            })

            def format_worksheet(worksheet, df, sheet_name):
                """Formatta un worksheet con stili consistenti"""
                # Scrivi headers
                for col_num, col_name in enumerate(df.columns):
                    worksheet.write(0, col_num, col_name, header_format)
                
                # Scrivi dati con formattazione appropriata
                for row_num, row_data in enumerate(df.itertuples(index=False), 1):
                    for col_num, value in enumerate(row_data):
                        col_name = df.columns[col_num]
                        
                        # Scegli il formato appropriato basato sul contenuto
                        if pd.isna(value):
                            worksheet.write(row_num, col_num, "", cell_format)
                        elif col_name in ["Numero occorrenze", "Occorrenze", "Numero fonti", "Fonte #"]:
                            worksheet.write(row_num, col_num, value, number_format)
                        elif "%" in str(col_name):
                            percentage_value = value/100 if isinstance(value, (int, float)) and value > 1 else value
                            worksheet.write(row_num, col_num, percentage_value, percentage_format)
                        elif col_name in ["AI Overview", "Il mio sito compare", "In SERP", "In AI Overview", "Ha AI Overview", "Proprio Sito in AI"]:
                            worksheet.write(row_num, col_num, value, cell_center_format)
                        else:
                            worksheet.write(row_num, col_num, value, cell_format)
                
                # Auto-adjust column widths intelligentemente
                for col_num, col_name in enumerate(df.columns):
                    # Calcola larghezza ottimale
                    max_length = len(str(col_name))
                    for row_data in df.itertuples(index=False):
                        cell_value = str(row_data[col_num]) if pd.notna(row_data[col_num]) else ""
                        max_length = max(max_length, len(cell_value))
                    
                    # Applica larghezze specifiche per colonne particolari
                    if col_name == "Analisi AI Overview":
                        adjusted_width = 80  # Extra large per analisi completa
                    elif "URL" in col_name or "Link" in col_name:
                        adjusted_width = 50
                    elif col_name in ["Testo AI Overview"]:
                        adjusted_width = 60
                    elif col_name in ["Dati strutturati SERP"]:
                        adjusted_width = 40
                    else:
                        adjusted_width = min(max(max_length + 3, 15), 50)
                    
                    worksheet.set_column(col_num, col_num, adjusted_width)
                
                # Freeze della prima riga (headers)
                worksheet.freeze_panes(1, 0)
                
                # Imposta altezza righe per text wrapping ottimale
                worksheet.set_row(0, 30)  # Header più alto
                for row_num in range(1, len(df) + 1):
                    # Calcola altezza in base al contenuto delle celle con più testo
                    max_lines = 1
                    for col_num, value in enumerate(df.iloc[row_num-1]):
                        if pd.notna(value) and isinstance(value, str):
                            lines = len(value) // 50 + 1  # Stima linee necessarie
                            max_lines = max(max_lines, lines)
                    
                    row_height = min(max(max_lines * 15, 25), 200)  # Min 25, max 200
                    worksheet.set_row(row_num, row_height)
            
            # Scrivi e formatta ogni sheet
            
            # 1. Analisi Keyword (primo tab)
            keyword_analysis_df.to_excel(writer, sheet_name="Analisi Keyword", index=False, header=False)
            worksheet_kw = writer.sheets["Analisi Keyword"]
            format_worksheet(worksheet_kw, keyword_analysis_df, "Analisi Keyword")
            
            # 2. Top Domains con grafico
            domains_df.to_excel(writer, sheet_name="Top Domains", index=False, header=False)
            worksheet_domains = writer.sheets["Top Domains"]
            format_worksheet(worksheet_domains, domains_df, "Top Domains")
            
            # Grafico a colonne per Top 10 domini
            chart_domains = workbook.add_chart({'type': 'column'})
            max_rows = min(10, len(domains_df))
            chart_domains.add_series({
                'name': 'Occorrenze',
                'categories': ['Top Domains', 1, 0, max_rows, 0],
                'values': ['Top Domains', 1, 1, max_rows, 1],
                'fill': {'color': '#1f77b4'},
                'data_labels': {'value': True}
            })
            chart_domains.set_title({
                'name': 'Top 10 Domini per Occorrenze', 
                'name_font': {'name': 'Work Sans', 'size': 14, 'bold': True}
            })
            chart_domains.set_x_axis({'name': 'Domini', 'name_font': {'name': 'Work Sans'}})
            chart_domains.set_y_axis({'name': 'Occorrenze', 'name_font': {'name': 'Work Sans'}})
            chart_domains.set_size({'width': 600, 'height': 400})
            worksheet_domains.insert_chart('E2', chart_domains)
            
            # 3. Competitor e tipologie con grafico
            domain_page_types_df.to_excel(writer, sheet_name="Competitor e Tipologie", index=False, header=False)
            worksheet_comp = writer.sheets["Competitor e Tipologie"]
            format_worksheet(worksheet_comp, domain_page_types_df, "Competitor e Tipologie")
            
            # Grafico a barre stack per tipologie
            chart_comp = workbook.add_chart({'type': 'bar', 'subtype': 'stacked'})
            page_types = ['Homepage', 'Pagina di Categoria', 'Pagina Prodotto', 'Articolo di Blog', 'Pagina di Servizi', 'Altro']
            colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b']
            
            max_comp_rows = min(10, len(domain_page_types_df))
            for i, page_type in enumerate(page_types):
                if page_type in domain_page_types_df.columns:
                    col_index = domain_page_types_df.columns.get_loc(page_type)
                    chart_comp.add_series({
                        'name': page_type,
                        'categories': ['Competitor e Tipologie', 1, 0, max_comp_rows, 0],
                        'values': ['Competitor e Tipologie', 1, col_index, max_comp_rows, col_index],
                        'fill': {'color': colors[i % len(colors)]},
                    })
            
            chart_comp.set_title({
                'name': 'Tipologie di Pagine per Competitor', 
                'name_font': {'name': 'Work Sans', 'size': 14, 'bold': True}
            })
            chart_comp.set_x_axis({'name': 'Occorrenze', 'name_font': {'name': 'Work Sans'}})
            chart_comp.set_y_axis({'name': 'Domini', 'name_font': {'name': 'Work Sans'}})
            chart_comp.set_size({'width': 800, 'height': 500})
            worksheet_comp.insert_chart('L2', chart_comp)
            
            # 4. Altri sheet con formattazione
            ai_overview_df.to_excel(writer, sheet_name="AI Overview", index=False, header=False)
            worksheet_ai = writer.sheets["AI Overview"]
            format_worksheet(worksheet_ai, ai_overview_df, "AI Overview")
            
            ai_sources_df.to_excel(writer, sheet_name="AI Overview Sources", index=False, header=False)
            worksheet_ai_sources = writer.sheets["AI Overview Sources"]
            format_worksheet(worksheet_ai_sources, ai_sources_df, "AI Overview Sources")
            
            if not own_site_df.empty:
                own_site_df.to_excel(writer, sheet_name="Tracking Proprio Sito", index=False, header=False)
                worksheet_own = writer.sheets["Tracking Proprio Sito"]
                format_worksheet(worksheet_own, own_site_df, "Tracking Proprio Sito")
            
            if not ai_analysis_df.empty:
                ai_analysis_df.to_excel(writer, sheet_name="Analisi AI Overview Pages", index=False, header=False)
                worksheet_ai_analysis = writer.sheets["Analisi AI Overview Pages"]
                format_worksheet(worksheet_ai_analysis, ai_analysis_df, "Analisi AI Overview Pages")
            
            if not structured_data_df.empty:
                structured_data_df.to_excel(writer, sheet_name="Dati Strutturati SERP", index=False, header=False)
                worksheet_struct = writer.sheets["Dati Strutturati SERP"]
                format_worksheet(worksheet_struct, structured_data_df, "Dati Strutturati SERP")
            
            # Keyword Clustering
            if keyword_clusters:
                clustering_data = []
                for cluster_name, keywords in keyword_clusters.items():
                    for keyword in keywords:
                        clustering_data.append({
                            "Cluster": cluster_name,
                            "Keyword": keyword
                        })
                clustering_df = pd.DataFrame(clustering_data)
                clustering_df.to_excel(writer, sheet_name="Keyword Clustering", index=False, header=False)
                worksheet_clustering = writer.sheets["Keyword Clustering"]
                format_worksheet(worksheet_clustering, clustering_df, "Keyword Clustering")

        return output.getvalue(), domains_df, own_site_df, ai_analysis_df, structured_data_df, keyword_analysis_df

def main():
    st.markdown('<h1 class="main-header">🔍 SERP Analyzer Plus Ultra</h1>', unsafe_allow_html=True)
    st.markdown("### 🚀 Analisi SERP avanzata con AI Overview, tracking sito e dati strutturati")
    st.markdown("---")

    st.sidebar.header("⚙️ Configurazione")
    
    serpapi_key = st.sidebar.text_input(
        "SERPApi Key", 
        type="password",
        help="Inserisci la tua API key di SERPApi.com"
    )
    
    openai_api_key = st.sidebar.text_input(
        "OpenAI API Key", 
        type="password",
        help="Inserisci la tua API key di OpenAI"
    )

    # Input per il proprio sito
    st.sidebar.subheader("🏠 Tracking Proprio Sito")
    own_site_url = st.sidebar.text_input(
        "URL del tuo sito (opzionale)",
        placeholder="es: miosito.com",
        help="Inserisci il dominio del tuo sito per trackarne la presenza nelle SERP e AI Overview"
    )
    
    # Estrai il dominio se fornito
    own_site_domain = None
    if own_site_url.strip():
        if not own_site_url.startswith(('http://', 'https://')):
            own_site_url = 'https://' + own_site_url
        own_site_domain = urlparse(own_site_url).netloc

    st.sidebar.subheader("🌍 Parametri di Ricerca")
    country = st.sidebar.selectbox(
        "Paese",
        ["it", "us", "uk", "de", "fr", "es"],
        index=0,
        help="Seleziona il paese per la ricerca"
    )
    
    language = st.sidebar.selectbox(
        "Lingua",
        ["it", "en", "de", "fr", "es"],
        index=0,
        help="Seleziona la lingua dei risultati"
    )
    
    num_results = st.sidebar.slider(
        "Numero di risultati per query",
        min_value=5,
        max_value=20,
        value=10,
        help="Numero di risultati da analizzare per ogni query"
    )
    
    st.sidebar.subheader("⚡ Opzioni Avanzate")
    use_ai_classification = st.sidebar.checkbox(
        "Usa AI per classificazione avanzata",
        value=True,
        help="Disabilita per analisi ultra-veloce (solo regole)"
    )
    
    enable_keyword_clustering = st.sidebar.checkbox(
        "Abilita clustering semantico keyword",
        value=True,
        help="Raggruppa le keyword per gruppi semantici"
    )
    
    # Cluster personalizzati
    custom_clusters = []
    if enable_keyword_clustering:
        st.sidebar.subheader("🏗️ Cluster Personalizzati (Opzionale)")
        custom_clusters_input = st.sidebar.text_area(
            "Nomi delle pagine/categorie del tuo sito",
            height=100,
            placeholder="Servizi SEO\nCorsi Online\nConsulenza Marketing\nBlog Aziendale\nChi Siamo",
            help="Inserisci i nomi delle tue pagine principali, uno per riga. Le keyword verranno assegnate prioritariamente a questi cluster."
        )
        
        if custom_clusters_input.strip():
            custom_clusters = [c.strip() for c in custom_clusters_input.strip().split('\n') if c.strip()]
            st.sidebar.success(f"✅ {len(custom_clusters)} cluster personalizzati definiti")
    
    # Opzioni per analisi avanzate
    enable_ai_overview_analysis = st.sidebar.checkbox(
        "Analizza pagine in AI Overview",
        value=True,
        help="Analizza il contenuto delle pagine che appaiono in AI Overview"
    )
    
    enable_structured_data_analysis = st.sidebar.checkbox(
        "Analizza dati strutturati",
        value=True,
        help="Estrai e analizza i dati strutturati delle prime pagine SERP"
    )
    
    max_pages_analysis = st.sidebar.slider(
        "Pagine da analizzare per query",
        min_value=3,
        max_value=10,
        value=5,
        help="Numero di pagine top SERP da analizzare per dati strutturati"
    )

    # Reset analisi
    if st.sidebar.button("🔄 Reset Analisi"):
        st.session_state.analysis_complete = False
        st.session_state.analysis_data = {}
        st.rerun()

    st.header("📝 Inserisci le Query")
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        queries_input = st.text_area(
            "Query da analizzare (una per riga)",
            height=200,
            placeholder="Inserisci le tue keyword qui...\nUna per ogni riga\n\nEsempio:\ncorso python\ncorso programmazione\nlearn python online"
        )
    
    with col2:
        st.markdown("### 💡 Funzionalità Nuove")
        st.info("""
        ✨ **Novità v2.0:**
        • 🏠 Tracking del tuo sito
        • 🤖 Analisi AI Overview  
        • 📊 Dati strutturati SERP
        • 🔍 Suggerimenti AI per ottimizzazione
        • 📈 Grafici Excel integrati
        • 🎯 Report keyword unificato
        • 🏗️ Cluster personalizzati
        """)

    # Mostra risultati se l'analisi è stata completata
    if st.session_state.analysis_complete and st.session_state.analysis_data:
        display_results(st.session_state.analysis_data)
    
    if st.button("🚀 Avvia Analisi Avanzata", type="primary", use_container_width=True):
        if use_ai_classification and (not serpapi_key or not openai_api_key):
            st.error("⚠️ Inserisci entrambe le API keys per l'analisi AI!")
            return
        elif not use_ai_classification and not serpapi_key:
            st.error("⚠️ Inserisci almeno la SERPApi key!")
            return
        
        if not queries_input.strip():
            st.error("⚠️ Inserisci almeno una query!")
            return

        queries = [q.strip() for q in queries_input.strip().split('\n') if q.strip()]
        
        if len(queries) > 100:  # Ridotto per le analisi avanzate
            st.error("⚠️ Massimo 100 query per l'analisi avanzata!")
            return

        # Esegui analisi
        results = run_analysis(
            queries, serpapi_key, openai_api_key, own_site_domain,
            country, language, num_results, use_ai_classification,
            enable_keyword_clustering, enable_ai_overview_analysis,
            enable_structured_data_analysis, max_pages_analysis, custom_clusters
        )
        
        if results:
            # Salva risultati in session state
            st.session_state.analysis_data = results
            st.session_state.analysis_complete = True
            
            # Mostra risultati
            display_results(results)

    st.markdown("---")
    st.markdown("""
    <div style='text-align: center; color: #666;'>
        <p>🚀 SERP Analyzer Plus Ultra - Sviluppato da Daniele e il suo amico Claude 🦕</p>
    </div>
    """, unsafe_allow_html=True)

def run_analysis(queries, serpapi_key, openai_api_key, own_site_domain,
                country, language, num_results, use_ai_classification,
                enable_keyword_clustering, enable_ai_overview_analysis,
                enable_structured_data_analysis, max_pages_analysis, custom_clusters=None):
    """Esegue l'analisi completa"""
    
    # Inizializza analyzer con il proprio sito
    analyzer = EnhancedSERPAnalyzer(serpapi_key, openai_api_key, own_site_domain)
    analyzer.use_ai = use_ai_classification

    if own_site_domain:
        st.info(f"🏠 Tracciamento attivato per: {own_site_domain}")

    # Clustering keywords se abilitato
    keyword_clusters = {}
    if enable_keyword_clustering and use_ai_classification:
        with st.spinner("🧠 Clustering semantico delle keyword..."):
            try:
                if custom_clusters:
                    # Usa clustering personalizzato
                    keyword_clusters = analyzer.cluster_keywords_with_custom(queries, custom_clusters)
                    st.success(f"✅ Cluster creati: {len(keyword_clusters)} (inclusi {len([k for k in keyword_clusters.keys() if k in custom_clusters])} personalizzati)")
                    
                    # Mostra preview cluster personalizzati
                    with st.expander("👀 Preview Clustering Personalizzato"):
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            st.write("**Cluster Personalizzati Utilizzati:**")
                            for cluster_name in custom_clusters:
                                if cluster_name in keyword_clusters and keyword_clusters[cluster_name]:
                                    st.write(f"✅ **{cluster_name}** ({len(keyword_clusters[cluster_name])} keyword)")
                                else:
                                    st.write(f"⚪ **{cluster_name}** (nessuna keyword assegnata)")
                        
                        with col2:
                            st.write("**Cluster Aggiuntivi Creati:**")
                            additional_clusters = [k for k in keyword_clusters.keys() if k not in custom_clusters]
                            for cluster_name in additional_clusters[:5]:
                                st.write(f"🆕 **{cluster_name}** ({len(keyword_clusters[cluster_name])} keyword)")
                            if len(additional_clusters) > 5:
                                st.write(f"... e altri {len(additional_clusters) - 5} cluster")
                else:
                    # Usa clustering automatico
                    keyword_clusters = analyzer.cluster_keywords_semantic(queries)
                    st.success(f"✅ Identificati {len(keyword_clusters)} cluster semantici!")
                    
                    with st.expander("👀 Preview Clustering Automatico"):
                        for cluster_name, keywords in list(keyword_clusters.items())[:3]:
                            st.write(f"**{cluster_name}** ({len(keywords)} keyword)")
                            st.write(", ".join(keywords[:10]) + ("..." if len(keywords) > 10 else ""))
            except Exception as e:
                st.warning(f"Errore durante il clustering: {e}")
                keyword_clusters = {}

    # Inizializza strutture dati per le nuove analisi
    all_domains = []
    query_page_types = defaultdict(list)
    domain_page_types = defaultdict(lambda: defaultdict(int))
    domain_occurences = defaultdict(int)
    paa_questions = []
    related_queries = []
    paa_to_queries = defaultdict(set)
    related_to_queries = defaultdict(set)
    paa_to_domains = defaultdict(set)
    ai_overview_data = {}
    own_site_tracking = {}
    ai_analysis_data = []
    structured_data_analysis = []

    progress_bar = st.progress(0)
    status_text = st.empty()

    for i, query in enumerate(queries):
        status_text.text(f"🔍 Analizzando: {query} ({i+1}/{len(queries)})")
        
        # Fetch SERP results
        results = analyzer.fetch_serp_results(query, country, language, num_results)
        
        if results:
            # Parse risultati base
            (domain_page_types_query, domain_occurences_query, query_page_types_query,
             paa_questions_query, related_queries_query, paa_to_queries_query,
             related_to_queries_query, paa_to_domains_query, ai_overview_info, 
             own_site_data, organic_results) = analyzer.parse_results(results, query)
            
            # Salva dati base
            ai_overview_data[query] = ai_overview_info
            own_site_tracking[query] = own_site_data
            
            # Aggiungi info AI Overview al tracking proprio sito
            if own_site_domain:
                own_site_tracking[query]["in_ai_overview"] = ai_overview_info.get("own_site_in_ai", False)
                own_site_tracking[query]["ai_overview_position"] = ai_overview_info.get("own_site_ai_position", None)

            # Merge dati
            for domain, page_types in domain_page_types_query.items():
                for page_type, count in page_types.items():
                    domain_page_types[domain][page_type] += count
            
            for domain, count in domain_occurences_query.items():
                domain_occurences[domain] += count
            
            query_page_types[query].extend(query_page_types_query[query])
            paa_questions.extend(paa_questions_query)
            related_queries.extend(related_queries_query)
            all_domains.extend(domain_page_types_query.keys())

            # NUOVE ANALISI AVANZATE
            
            # 1. Analisi pagine AI Overview
            if enable_ai_overview_analysis and ai_overview_info["has_ai_overview"] and ai_overview_info["ai_sources"]:
                status_text.text(f"🤖 Analizzando AI Overview per: {query}")
                try:
                    ai_analysis_results = analyzer.analyze_ai_overview_pages(ai_overview_info, query)
                    ai_analysis_data.extend(ai_analysis_results)
                except Exception as e:
                    st.warning(f"Errore analisi AI Overview per '{query}': {e}")

            # 2. Analisi dati strutturati SERP
            if enable_structured_data_analysis and organic_results:
                status_text.text(f"📊 Analizzando dati strutturati per: {query}")
                try:
                    structured_results = analyzer.analyze_top_serp_structured_data(
                        organic_results, query, max_pages_analysis
                    )
                    structured_data_analysis.extend(structured_results)
                except Exception as e:
                    st.warning(f"Errore analisi dati strutturati per '{query}': {e}")
        
        progress_bar.progress((i + 1) / len(queries))
        time.sleep(1.0)  # Rate limiting per le analisi avanzate

    status_text.text("✅ Analisi completata! Generazione report avanzato...")

    # Genera report Excel avanzato
    domains_counter = Counter(all_domains)
    excel_data, domains_df, own_site_df, ai_analysis_df, structured_data_df, keyword_analysis_df = analyzer.create_enhanced_excel_report(
        domains_counter, domain_occurences, query_page_types, domain_page_types,
        paa_questions, related_queries, paa_to_queries, related_to_queries, paa_to_domains, 
        ai_overview_data, own_site_tracking, ai_analysis_data, structured_data_analysis, keyword_clusters
    )

    progress_bar.empty()
    status_text.empty()
    
    return {
        'excel_data': excel_data,
        'domains_df': domains_df,
        'own_site_df': own_site_df,
        'ai_analysis_df': ai_analysis_df,
        'structured_data_df': structured_data_df,
        'keyword_analysis_df': keyword_analysis_df,
        'ai_overview_data': ai_overview_data,
        'own_site_tracking': own_site_tracking,
        'ai_analysis_data': ai_analysis_data,
        'structured_data_analysis': structured_data_analysis,
        'queries': queries,
        'own_site_domain': own_site_domain
    }

def display_results(results):
    """Mostra i risultati dell'analisi"""
    
    domains_df = results['domains_df']
    own_site_df = results['own_site_df']
    ai_analysis_df = results['ai_analysis_df']
    structured_data_df = results['structured_data_df']
    keyword_analysis_df = results['keyword_analysis_df']
    ai_overview_data = results['ai_overview_data']
    own_site_tracking = results['own_site_tracking']
    ai_analysis_data = results['ai_analysis_data']
    structured_data_analysis = results['structured_data_analysis']
    queries = results['queries']
    own_site_domain = results['own_site_domain']
    
    # VISUALIZZAZIONE RISULTATI POTENZIATA
    st.markdown("---")
    st.header("📊 Risultati Analisi Avanzata")

    # Metriche principali
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    
    with col1:
        st.metric("Query Analizzate", len(queries))
    with col2:
        st.metric("Domini Trovati", len(domains_df))
    with col3:
        ai_overview_count = sum(1 for ai_info in ai_overview_data.values() if ai_info["has_ai_overview"])
        st.metric("Query con AI Overview", ai_overview_count)
    with col4:
        if own_site_domain:
            own_serp_count = sum(1 for data in own_site_tracking.values() if data["in_serp"])
            st.metric("Tuo Sito in SERP", own_serp_count)
    with col5:
        if own_site_domain:
            own_ai_count = sum(1 for data in own_site_tracking.values() if data.get("in_ai_overview", False))
            st.metric("Tuo Sito in AI Overview", own_ai_count)
    with col6:
        st.metric("Pagine Analizzate", len(ai_analysis_data) + len(structured_data_analysis))

    # Tracking proprio sito (se abilitato)
    if own_site_domain and not own_site_df.empty:
        st.markdown("---")
        st.header("🏠 Performance del Tuo Sito")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # Grafico presenza SERP vs AI Overview
            own_site_summary = {
                "Solo SERP": len(own_site_df[(own_site_df["In SERP"] == True) & (own_site_df["In AI Overview"] == False)]),
                "Solo AI Overview": len(own_site_df[(own_site_df["In SERP"] == False) & (own_site_df["In AI Overview"] == True)]),
                "SERP + AI Overview": len(own_site_df[(own_site_df["In SERP"] == True) & (own_site_df["In AI Overview"] == True)]),
                "Assente": len(queries) - len(own_site_df)
            }
            
            fig_own = px.pie(
                values=list(own_site_summary.values()),
                names=list(own_site_summary.keys()),
                title="Distribuzione Presenza del Tuo Sito"
            )
            st.plotly_chart(fig_own, use_container_width=True)
        
        with col2:
            st.subheader("📋 Dettagli Performance")
            st.dataframe(own_site_df, use_container_width=True)

    # Analisi AI Overview avanzata
    if ai_analysis_data:
        st.markdown("---")
        st.header("🤖 Analisi Approfondita AI Overview")
        
        # Domini più presenti in AI Overview
        ai_domains = [item["domain"] for item in ai_analysis_data]
        ai_domain_counter = Counter(ai_domains)
        
        col1, col2 = st.columns(2)
        
        with col1:
            ai_domains_df = pd.DataFrame(
                ai_domain_counter.most_common(10),
                columns=["Dominio", "Presenze in AI Overview"]
            )
            
            fig_ai_domains = px.bar(
                ai_domains_df,
                x="Presenze in AI Overview",
                y="Dominio",
                orientation="h",
                title="Top Domini in AI Overview"
            )
            st.plotly_chart(fig_ai_domains, use_container_width=True)
        
        with col2:
            # Mostra esempio di analisi AI
            if ai_analysis_data:
                st.subheader("💡 Esempio Analisi AI")
                example = ai_analysis_data[0]
                st.write(f"**Query:** {example['query']}")
                st.write(f"**URL:** {example['url']}")
                st.write(f"**Posizione:** {example['position_in_ai']}")
                with st.expander("Vedi analisi completa"):
                    st.write(example['ai_analysis'])

    # Analisi dati strutturati
    if structured_data_analysis:
        st.markdown("---")
        st.header("📊 Analisi Dati Strutturati SERP")
        
        # Schema types più comuni
        all_schemas = []
        for item in structured_data_analysis:
            if item.get('schema_types'):
                all_schemas.extend([s.strip() for s in item['schema_types'].split(',')])
        
        if all_schemas:
            schema_counter = Counter(all_schemas)
            schema_df = pd.DataFrame(
                schema_counter.most_common(10),
                columns=["Schema Type", "Occorrenze"]
            )
            
            fig_schema = px.bar(
                schema_df,
                x="Occorrenze",
                y="Schema Type",
                orientation="h",
                title="Schema Types più Utilizzati"
            )
            st.plotly_chart(fig_schema, use_container_width=True)

    # Grafici esistenti (domini, tipologie, etc.) - ORDINATI
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📈 Top Domini")
        if not domains_df.empty:
            # Già ordinato nella funzione create_enhanced_excel_report
            fig_domains = px.bar(
                domains_df.head(10), 
                x="Dominio", 
                y="Occorrenze",
                title="Top 10 Domini per Occorrenze"
            )
            fig_domains.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig_domains, use_container_width=True)

    with col2:
        # AI Overview vs SERP tradizionale
        ai_vs_serp = {
            "Con AI Overview": ai_overview_count,
            "Solo SERP tradizionale": len(queries) - ai_overview_count
        }
        
        fig_ai_vs_serp = px.pie(
            values=list(ai_vs_serp.values()),
            names=list(ai_vs_serp.keys()),
            title="AI Overview vs SERP Tradizionale"
        )
        st.plotly_chart(fig_ai_vs_serp, use_container_width=True)

    # Tabelle dettagliate
    st.subheader("📋 Report Dettagliati")
    
    tabs = ["Analisi Keyword", "Top Domini", "AI Overview"]
    if not own_site_df.empty:
        tabs.append("Tracking Sito")
    if ai_analysis_data:
        tabs.append("Analisi AI Overview")
    if structured_data_analysis:
        tabs.append("Dati Strutturati")
    
    tab_objects = st.tabs(tabs)
    
    current_tab = 0
    
    # NUOVO TAB: Analisi Keyword (primo tab)
    with tab_objects[current_tab]:
        st.subheader("🎯 Analisi Completa per Keyword")
        st.dataframe(keyword_analysis_df, use_container_width=True)
    current_tab += 1
    
    with tab_objects[current_tab]:  # Top Domini
        st.dataframe(domains_df, use_container_width=True)
    current_tab += 1
    
    with tab_objects[current_tab]:  # AI Overview
        ai_overview_list = []
        for query, ai_info in ai_overview_data.items():
            ai_overview_list.append({
                "Query": query,
                "Ha AI Overview": ai_info["has_ai_overview"],
                "Numero Fonti": len(ai_info["ai_sources"]),
                "Tuo Sito in AI": ai_info.get("own_site_in_ai", False),
                "Posizione Tuo Sito": ai_info.get("own_site_ai_position", "")
            })
        
        ai_overview_summary_df = pd.DataFrame(ai_overview_list)
        st.dataframe(ai_overview_summary_df, use_container_width=True)
    current_tab += 1
    
    if not own_site_df.empty:  # Tracking Sito
        with tab_objects[current_tab]:
            st.dataframe(own_site_df, use_container_width=True)
        current_tab += 1
    
    if ai_analysis_data:  # Analisi AI Overview
        with tab_objects[current_tab]:
            st.dataframe(ai_analysis_df, use_container_width=True)
        current_tab += 1
    
    if structured_data_analysis:  # Dati Strutturati
        with tab_objects[current_tab]:
            st.dataframe(structured_data_df, use_container_width=True)

    # Download report
    st.subheader("💾 Download Report Avanzato")
    st.download_button(
        label="📥 Scarica Report Excel Completo",
        data=results['excel_data'],
        file_name=f"serp_analysis_enhanced_{time.strftime('%Y%m%d_%H%M%S')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="download_report"  # Chiave unica per evitare conflitti
    )

    st.success("🎉 Analisi avanzata completata con successo!")

if __name__ == "__main__":
    main()
