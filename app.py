import os
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests as httpRequest
from scholarly import scholarly, ProxyGenerator
from rank_bm25 import BM25Okapi
import nltk
import logging
from xml.etree import ElementTree as ET
import ollama
import random

# --- Setup ---
app = Flask(__name__,
            static_folder='.',
            static_url_path='',
            template_folder='templates')
CORS(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    nltk.data.find('tokenizers/punkt')
except nltk.downloader.DownloadError:
    logger.info("NLTK 'punkt' tokenizer not found. Downloading...")
    nltk.download('punkt')
    logger.info("'punkt' downloaded.")

# --- Helper Functions ---
def tokenize(text):
    if not text:
        return []
    return nltk.word_tokenize(text.lower())

# --- Proxy Setup for Scholarly (Simplified) ---
proxies = []
proxy_file_path = 'proxies.txt'

def load_proxies():
    """Load proxies from file if available"""
    global proxies
    if os.path.exists(proxy_file_path):
        with open(proxy_file_path, 'r') as f:
            proxies = [line.strip() for line in f if line.strip()]
        logger.info(f"Loaded {len(proxies)} proxies from {proxy_file_path}")
    else:
        logger.warning(f"Proxy file not found: {proxy_file_path}. Scholarly will operate without proxies.")

def set_scholarly_proxy():
    """Configure scholarly to use a proxy if available"""
    if not proxies:
        logger.warning("No proxies loaded. Scholarly will attempt direct connection.")
        scholarly.use_proxy(None)
        return
    
    # Use a random proxy from the list
    selected_proxy = random.choice(proxies)
    logger.info(f"Attempting to use proxy: {selected_proxy}")
    
    try:
        pg = ProxyGenerator()
        # Note: This is a simplified proxy setup. Production use may require more robust configuration.
        scholarly.use_proxy(pg)
        logger.info("Proxy configured for scholarly")
    except Exception as e:
        logger.warning(f"Could not configure proxy: {e}. Continuing without proxy.")
        scholarly.use_proxy(None)

# Load proxies on startup
load_proxies()

# --- API Routes ---

@app.route('/api/search-pubmed', methods=['POST'])
def search_pubmed_route():
    """Search PubMed for research papers"""
    data = request.json
    query = data.get('query')
    max_results = int(data.get('max_results', 10))
    filters = data.get('filters', {})

    if not query:
        return jsonify({"error": "Query is required"}), 400
    logger.info(f"Received PubMed search: query='{query}', max_results={max_results}, filters={filters}")

    eutils_base = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/'
    papers = []
    try:
        term = query
        year_start_filter = filters.get('yearStart')
        year_end_filter = filters.get('yearEnd')
        date_filter_string = ""
        if year_start_filter or year_end_filter:
            start_date_pubmed = str(year_start_filter) if year_start_filter else "1000"
            end_date_pubmed = str(year_end_filter) if year_end_filter else "3000"
            date_filter_string = f" AND ({start_date_pubmed}[Date - Publication]:{end_date_pubmed}[Date - Publication])"
        term += date_filter_string

        search_params = {'db': 'pubmed', 'term': term, 'retmax': max_results, 'usehistory': 'y', 'retmode': 'json', 'sort': 'relevance'}
        logger.info(f"PubMed ESearch params: {search_params}")
        search_resp = httpRequest.get(f"{eutils_base}esearch.fcgi", params=search_params, timeout=30)
        search_resp.raise_for_status()
        search_data = search_resp.json()
        logger.debug(f"PubMed ESearch response data: {search_data}")

        id_list = search_data.get("esearchresult", {}).get("idlist")
        if not id_list:
            logger.info("No PubMed IDs found for the query.")
            return jsonify([])

        fetch_params = {'db': 'pubmed', 'id': ','.join(id_list), 'retmode': 'xml'}
        logger.info(f"PubMed EFetch params: {fetch_params}")
        fetch_resp = httpRequest.post(f"{eutils_base}efetch.fcgi", data=fetch_params, timeout=45)
        fetch_resp.raise_for_status()
        
        root = ET.fromstring(fetch_resp.content)
        for article_et in root.findall('.//PubmedArticle'):
            pmid_node = article_et.find('.//PMID')
            pmid = pmid_node.text if pmid_node is not None else None
            article_title_node = article_et.find('.//ArticleTitle')
            title_parts = [text_part for text_part in article_title_node.itertext()] if article_title_node is not None else []
            title = "".join(title_parts).strip() if title_parts else 'N/A'
            
            abstract_text_nodes = article_et.findall('.//AbstractText')
            abstract_parts = []
            if abstract_text_nodes:
                for node in abstract_text_nodes:
                    node_text_parts = [text_part for text_part in node.itertext()]
                    node_text = "".join(node_text_parts).strip()
                    if node_text:
                        label = node.get('Label')
                        abstract_parts.append(f"{label}: {node_text}" if label else node_text)
                abstract = "\n".join(abstract_parts) if abstract_parts else "No abstract available."
            else:
                abstract = "No abstract available."

            author_list_node = article_et.find('.//AuthorList')
            authors = []
            if author_list_node is not None:
                for author_node in author_list_node.findall('.//Author'):
                    last_name_node = author_node.find('.//LastName')
                    fore_name_node = author_node.find('.//ForeName')
                    initials_node = author_node.find('.//Initials')
                    last_name = last_name_node.text if last_name_node is not None and last_name_node.text else ""
                    fore_name = fore_name_node.text if fore_name_node is not None and fore_name_node.text else ""
                    initials = initials_node.text if initials_node is not None and initials_node.text else ""
                    author_name = ""
                    if fore_name and last_name: author_name = f"{fore_name} {last_name}"
                    elif last_name and initials: author_name = f"{initials} {last_name}"
                    elif last_name: author_name = last_name
                    elif fore_name: author_name = fore_name
                    if author_name: authors.append(author_name.strip())
            
            pub_date_node = article_et.find('.//ArticleDate') or article_et.find('.//PubDate')
            year_val, pub_date_str = None, "N/A"
            if pub_date_node is not None:
                year_node = pub_date_node.find('.//Year')
                if year_node is not None and year_node.text:
                    try:
                        year_val = int(year_node.text)
                        month_node = pub_date_node.find('.//Month')
                        day_node = pub_date_node.find('.//Day')
                        month_str = month_node.text if month_node is not None and month_node.text else "01"
                        try: month_val = int(month_str)
                        except ValueError:
                            month_map = {"jan": "01", "feb": "02", "mar": "03", "apr": "04", "may": "05", "jun": "06", "jul": "07", "aug": "08", "sep": "09", "oct": "10", "nov": "11", "dec": "12"}
                            month_val = month_map.get(month_str.lower()[:3], "01")
                        day_str = day_node.text if day_node is not None and day_node.text else "01"
                        pub_date_str = f"{year_val}-{str(month_val).zfill(2)}-{day_str.zfill(2)}"
                    except ValueError:
                        logger.warning(f"Could not parse year for PMID {pmid}: {year_node.text}")
                        pub_date_str = year_node.text
            
            doi_node = article_et.find('.//ArticleId[@IdType="doi"]')
            doi = doi_node.text if doi_node is not None else None
            papers.append({
                "id": f"pubmed_{pmid}", "title": title, "authors": authors, "abstract": abstract,
                "publishedDate": pub_date_str, "year": year_val,
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else (f"https://doi.org/{doi}" if doi else None),
                "pdfUrl": f"https://doi.org/{doi}" if doi else None, "source": "PubMed", "citations": None, "doi": doi,
                "relevanceScore": 0.6
            })
        logger.info(f"PubMed search successful, processed {len(papers)} articles.")
    except httpRequest.exceptions.RequestException as e:
        logger.error(f"Network error during PubMed search: {e}", exc_info=True)
        return jsonify({"error": f"Network error during PubMed search: {str(e)}"}), 503
    except ET.ParseError as e:
        logger.error(f"XML parsing error for PubMed results: {e}", exc_info=True)
        return jsonify({"error": "Failed to parse PubMed XML response."}), 500
    except Exception as e:
        logger.error(f"Error searching PubMed: {e}", exc_info=True)
        return jsonify({"error": f"Error searching PubMed: {str(e)}"}), 500
    return jsonify(papers)

@app.route('/api/search-scholar', methods=['POST'])
def search_google_scholar_route():
    """Search Google Scholar for research papers"""
    data = request.json
    query = data.get('query')
    max_results = int(data.get('max_results', 10))
    year_low = data.get('year_low')
    year_high = data.get('year_high')

    if not query:
        return jsonify({"error": "Query is required"}), 400
    logger.info(f"Received Google Scholar search request: query='{query}', max_results={max_results}")

    results = []
    try:
        # Set proxy before search
        set_scholarly_proxy()
        
        search_args = {'query': query}
        if year_low is not None: search_args['year_low'] = int(year_low)
        if year_high is not None: search_args['year_high'] = int(year_high)
        
        logger.info(f"Calling scholarly.search_pubs with args: {search_args}")
        search_results_gen = scholarly.search_pubs(**search_args)
        
        count = 0
        for item in search_results_gen:
            if count >= max_results: break
            
            bib = item.get('bib', {})
            abstract_text = bib.get('abstract', 'N/A')
            pub_year = bib.get('pub_year')
            try:
                year_int = int(pub_year) if pub_year else None
            except (ValueError, TypeError):
                year_int = None

            authors_data = bib.get('author')
            authors_list = []
            if isinstance(authors_data, str):
                authors_list = authors_data.split(' and ')
            elif isinstance(authors_data, list):
                authors_list = authors_data
            else:
                authors_list = []

            results.append({
                "id": f"scholar_{item.get('id_scholarcitedby', bib.get('title', f'untitled_{count}'))}",
                "title": bib.get('title', 'N/A'),
                "authors": authors_list,
                "abstract": abstract_text,
                "venue": bib.get('venue', None),
                "year": year_int,
                "publishedDate": f"{year_int}-01-01" if year_int else None,
                "url": item.get('pub_url', item.get('eprint_url', None)),
                "pdfUrl": item.get('eprint_url') if item.get('eprint_url') and "pdf" in item.get('eprint_url', "").lower() else None,
                "citations": bib.get('num_citations', 0),
                "source": "Google Scholar",
                "relevanceScore": 0.7
            })
            count += 1
        logger.info(f"Google Scholar search successful, found {len(results)} results.")
    except Exception as e:
        logger.error(f"Error scraping Google Scholar: {e}", exc_info=True)
        return jsonify({"error": f"Error scraping Google Scholar: {str(e)}"}), 500
    return jsonify(results)

@app.route('/api/search-arxiv', methods=['POST'])
def search_arxiv_route():
    """Search arXiv for research papers"""
    data = request.json
    query = data.get('query')
    max_results = int(data.get('max_results', 10))
    filters = data.get('filters', {})

    if not query:
        return jsonify({"error": "Query is required"}), 400
    logger.info(f"Received arXiv search: query='{query}', max_results={max_results}")

    papers = []
    try:
        # arXiv API endpoint
        arxiv_base = 'http://export.arxiv.org/api/query'
        
        # Build search query
        search_query = f'all:{query}'
        
        params = {
            'search_query': search_query,
            'start': 0,
            'max_results': max_results,
            'sortBy': 'relevance',
            'sortOrder': 'descending'
        }
        
        logger.info(f"arXiv search params: {params}")
        response = httpRequest.get(arxiv_base, params=params, timeout=30)
        response.raise_for_status()
        
        # Parse XML response
        root = ET.fromstring(response.content)
        
        # Define namespace
        ns = {
            'atom': 'http://www.w3.org/2005/Atom',
            'arxiv': 'http://arxiv.org/schemas/atom'
        }
        
        for entry in root.findall('atom:entry', ns):
            title_elem = entry.find('atom:title', ns)
            title = title_elem.text.strip() if title_elem is not None else 'N/A'
            
            summary_elem = entry.find('atom:summary', ns)
            abstract = summary_elem.text.strip() if summary_elem is not None else 'No abstract available.'
            
            # Get authors
            authors = []
            for author in entry.findall('atom:author', ns):
                name_elem = author.find('atom:name', ns)
                if name_elem is not None:
                    authors.append(name_elem.text.strip())
            
            # Get publication date
            published_elem = entry.find('atom:published', ns)
            published_date = published_elem.text[:10] if published_elem is not None else 'N/A'
            year_val = None
            if published_date != 'N/A':
                try:
                    year_val = int(published_date.split('-')[0])
                except:
                    pass
            
            # Get arXiv ID and URLs
            id_elem = entry.find('atom:id', ns)
            arxiv_url = id_elem.text if id_elem is not None else None
            arxiv_id = arxiv_url.split('/abs/')[-1] if arxiv_url else None
            pdf_url = f'http://arxiv.org/pdf/{arxiv_id}.pdf' if arxiv_id else None
            
            # Get DOI if available
            doi = None
            doi_elem = entry.find('arxiv:doi', ns)
            if doi_elem is not None:
                doi = doi_elem.text
            
            papers.append({
                "id": f"arxiv_{arxiv_id}",
                "title": title,
                "authors": authors,
                "abstract": abstract,
                "publishedDate": published_date,
                "year": year_val,
                "url": arxiv_url,
                "pdfUrl": pdf_url,
                "source": "arXiv",
                "citations": None,
                "doi": doi,
                "relevanceScore": 0.7
            })
        
        logger.info(f"arXiv search successful, processed {len(papers)} articles.")
    except httpRequest.exceptions.RequestException as e:
        logger.error(f"Network error during arXiv search: {e}", exc_info=True)
        return jsonify({"error": f"Network error during arXiv search: {str(e)}"}), 503
    except ET.ParseError as e:
        logger.error(f"XML parsing error for arXiv results: {e}", exc_info=True)
        return jsonify({"error": "Failed to parse arXiv XML response."}), 500
    except Exception as e:
        logger.error(f"Error searching arXiv: {e}", exc_info=True)
        return jsonify({"error": f"Error searching arXiv: {str(e)}"}), 500
    return jsonify(papers)

@app.route('/api/search-semantic-scholar', methods=['POST'])
def search_semantic_scholar_route():
    """Search Semantic Scholar for research papers"""
    data = request.json
    query = data.get('query')
    max_results = int(data.get('max_results', 10))

    if not query:
        return jsonify({"error": "Query is required"}), 400
    logger.info(f"Received Semantic Scholar search: query='{query}', max_results={max_results}")

    papers = []
    try:
        # Semantic Scholar API endpoint
        ss_base = 'https://api.semanticscholar.org/graph/v1/paper/search'
        
        params = {
            'query': query,
            'limit': min(max_results, 100),  # API limit is 100
            'fields': 'paperId,title,abstract,authors,year,publicationDate,url,citationCount,openAccessPdf'
        }
        
        logger.info(f"Semantic Scholar search params: {params}")
        response = httpRequest.get(ss_base, params=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        for paper in data.get('data', []):
            paper_id = paper.get('paperId')
            title = paper.get('title', 'N/A')
            abstract = paper.get('abstract', 'No abstract available.')
            
            # Get authors
            authors = []
            for author in paper.get('authors', []):
                authors.append(author.get('name', ''))
            
            year_val = paper.get('year')
            pub_date = paper.get('publicationDate', 'N/A')
            
            url = paper.get('url') or f'https://www.semanticscholar.org/paper/{paper_id}'
            
            # Get PDF URL if available
            pdf_url = None
            open_access = paper.get('openAccessPdf')
            if open_access:
                pdf_url = open_access.get('url')
            
            citations = paper.get('citationCount', 0)
            
            papers.append({
                "id": f"semantic_{paper_id}",
                "title": title,
                "authors": authors,
                "abstract": abstract,
                "publishedDate": pub_date,
                "year": year_val,
                "url": url,
                "pdfUrl": pdf_url,
                "source": "Semantic Scholar",
                "citations": citations,
                "doi": None,
                "relevanceScore": 0.75
            })
        
        logger.info(f"Semantic Scholar search successful, processed {len(papers)} articles.")
    except httpRequest.exceptions.RequestException as e:
        logger.error(f"Network error during Semantic Scholar search: {e}", exc_info=True)
        return jsonify({"error": f"Network error during Semantic Scholar search: {str(e)}"}), 503
    except Exception as e:
        logger.error(f"Error searching Semantic Scholar: {e}", exc_info=True)
        return jsonify({"error": f"Error searching Semantic Scholar: {str(e)}"}), 500
    return jsonify(papers)

@app.route('/api/search-crossref', methods=['POST'])
def search_crossref_route():
    """Search CrossRef for research papers"""
    data = request.json
    query = data.get('query')
    max_results = int(data.get('max_results', 10))

    if not query:
        return jsonify({"error": "Query is required"}), 400
    logger.info(f"Received CrossRef search: query='{query}', max_results={max_results}")

    papers = []
    try:
        # CrossRef API endpoint
        crossref_base = 'https://api.crossref.org/works'
        
        params = {
            'query': query,
            'rows': max_results,
            'sort': 'relevance',
            'order': 'desc'
        }
        
        logger.info(f"CrossRef search params: {params}")
        response = httpRequest.get(crossref_base, params=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        for item in data.get('message', {}).get('items', []):
            # Get DOI
            doi = item.get('DOI')
            
            # Get title
            title_list = item.get('title', [])
            title = title_list[0] if title_list else 'N/A'
            
            # Get abstract (often not available in CrossRef)
            abstract = item.get('abstract', 'No abstract available.')
            
            # Get authors
            authors = []
            for author in item.get('author', []):
                given = author.get('given', '')
                family = author.get('family', '')
                if given and family:
                    authors.append(f"{given} {family}")
                elif family:
                    authors.append(family)
            
            # Get publication date
            pub_date_parts = item.get('published', {}).get('date-parts', [[]])
            if pub_date_parts and pub_date_parts[0]:
                year_val = pub_date_parts[0][0] if len(pub_date_parts[0]) > 0 else None
                month = pub_date_parts[0][1] if len(pub_date_parts[0]) > 1 else 1
                day = pub_date_parts[0][2] if len(pub_date_parts[0]) > 2 else 1
                pub_date = f"{year_val}-{str(month).zfill(2)}-{str(day).zfill(2)}"
            else:
                year_val = None
                pub_date = 'N/A'
            
            # Get URL
            url = item.get('URL') or f'https://doi.org/{doi}' if doi else None
            
            # Get PDF URL if available
            pdf_url = None
            for link in item.get('link', []):
                if link.get('content-type') == 'application/pdf':
                    pdf_url = link.get('URL')
                    break
            
            citations = item.get('is-referenced-by-count', 0)
            
            papers.append({
                "id": f"crossref_{doi.replace('/', '_') if doi else 'unknown'}",
                "title": title,
                "authors": authors,
                "abstract": abstract,
                "publishedDate": pub_date,
                "year": year_val,
                "url": url,
                "pdfUrl": pdf_url,
                "source": "CrossRef",
                "citations": citations,
                "doi": doi,
                "relevanceScore": 0.65
            })
        
        logger.info(f"CrossRef search successful, processed {len(papers)} articles.")
    except httpRequest.exceptions.RequestException as e:
        logger.error(f"Network error during CrossRef search: {e}", exc_info=True)
        return jsonify({"error": f"Network error during CrossRef search: {str(e)}"}), 503
    except Exception as e:
        logger.error(f"Error searching CrossRef: {e}", exc_info=True)
        return jsonify({"error": f"Error searching CrossRef: {str(e)}"}), 500
    return jsonify(papers)

@app.route('/api/rank-bm25', methods=['POST'])
def rank_bm25_route():
    """Rank papers using BM25 algorithm"""
    data = request.json
    papers_data = data.get('papers')
    verbose_query = data.get('verbose_query')

    if not papers_data or not verbose_query:
        return jsonify({"error": "Papers data and verbose query are required"}), 400
    logger.info(f"Received BM25 ranking request. Papers: {len(papers_data)}, Query: '{verbose_query[:100]}...'")

    try:
        corpus = [str(paper.get('abstract', '')) for paper in papers_data]
        tokenized_corpus = [tokenize(doc) for doc in corpus]
        tokenized_query = tokenize(verbose_query)

        if not any(tokenized_corpus):
            logger.warning("BM25: Corpus is empty. Scores will be zero.")
            for paper in papers_data: paper['bm25_score'] = paper['relevanceScore'] = 0.0
            return jsonify(papers_data)
        if not tokenized_query:
            logger.warning("BM25: Query is empty. Scores will be zero.")
            for paper in papers_data: paper['bm25_score'] = paper['relevanceScore'] = 0.0
            return jsonify(papers_data)

        bm25 = BM25Okapi(tokenized_corpus)
        doc_scores = bm25.get_scores(tokenized_query)
        for paper, score in zip(papers_data, doc_scores):
            paper['bm25_score'] = float(score)
            paper['relevanceScore'] = float(score)
        logger.info("BM25 ranking successful.")
    except Exception as e:
        logger.error(f"Error during BM25 ranking: {e}", exc_info=True)
        for paper in papers_data: paper['bm25_score'] = paper['relevanceScore'] = 0.0
        return jsonify({"error": f"Error during BM25 ranking: {str(e)}", "ranked_papers_fallback": papers_data}), 500
    return jsonify(papers_data)

@app.route('/api/ollama-refine-query', methods=['POST'])
def ollama_refine_query():
    """Refine search query using Ollama AI"""
    data = request.json
    query = data.get('query')
    model = data.get('model', 'gemma:2b')

    if not query:
        return jsonify({"error": "Query is required"}), 400

    try:
        logger.info(f"Calling Ollama for query refinement with model '{model}' for query: '{query}'")
        prompt = f"Refine the following research paper search query to be more effective and comprehensive. Provide only the refined query, no additional text or explanation:\n\nOriginal query: \"{query}\"\n\nRefined query:"
        response = ollama.chat(model=model, messages=[{'role': 'user', 'content': prompt}])
        refined_query = response['message']['content'].strip()
        logger.info(f"Ollama refined query: '{refined_query}'")
        return jsonify({"refined_query": refined_query})
    except Exception as e:
        logger.error(f"Error refining query with Ollama: {e}", exc_info=True)
        return jsonify({"error": f"Error refining query with Ollama: {str(e)}"}), 500

@app.route('/api/ollama-summarize-abstract', methods=['POST'])
def ollama_summarize_abstract():
    """Summarize abstract using Ollama AI"""
    data = request.json
    abstract = data.get('abstract')
    model = data.get('model', 'gemma:2b')

    if not abstract:
        return jsonify({"error": "Abstract is required"}), 400

    try:
        logger.info(f"Calling Ollama for abstract summarization with model '{model}'")
        prompt = f"Summarize the following research paper abstract concisely. Provide only the summary, no additional text or explanation:\n\nAbstract: \"{abstract}\"\n\nSummary:"
        response = ollama.chat(model=model, messages=[{'role': 'user', 'content': prompt}])
        summary = response['message']['content'].strip()
        logger.info(f"Ollama summarized abstract")
        return jsonify({"summary": summary})
    except Exception as e:
        logger.error(f"Error summarizing abstract with Ollama: {e}", exc_info=True)
        return jsonify({"error": f"Error summarizing abstract with Ollama: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
