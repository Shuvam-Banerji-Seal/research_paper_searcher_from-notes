import os
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import requests as httpRequest
from scholarly import scholarly # Removed ProxyGenerator as it's not used in your current setup
from rank_bm25 import BM25Okapi
import nltk
import logging
from xml.etree import ElementTree as ET

# --- Setup ---
# Set the static_folder to the current directory '.'
# static_url_path means files are served from the root URL.
# template_folder points to your 'templates' directory.
app = Flask(__name__,
            static_folder='.', # Serve static files from the root project directory
            static_url_path='',
            template_folder='templates') # If you use render_template for anything
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

# --- Frontend Serving Routes ---
@app.route('/')
def serve_index():
    logger.info(f"Attempting to serve index.html from directory: {app.root_path}")
    # Try to send index.html from the root project directory
    if os.path.exists(os.path.join(app.root_path, 'index.html')):
        return send_from_directory(app.root_path, 'index.html')
    logger.error("index.html not found in root directory.")
    return "index.html not found", 404

@app.route('/<path:filename>')
def serve_static_or_template(filename):
    logger.info(f"Attempting to serve: {filename}")
    # Priority 1: Serve from root if it's a known frontend file (script.js, styles.css)
    # This explicit check is because '.' as static_folder can be broad.
    if filename in ['script.js', 'styles.css', 'index.html']: # Add other root static files if any
        if os.path.exists(os.path.join(app.root_path, filename)):
            logger.info(f"Serving '{filename}' from root project directory.")
            return send_from_directory(app.root_path, filename)

    # Priority 2: If you had a dedicated 'static' subfolder for other assets (images, etc.)
    # static_subfolder = os.path.join(app.root_path, 'static')
    # if os.path.exists(os.path.join(static_subfolder, filename)):
    #     logger.info(f"Serving '{filename}' from 'static' subfolder.")
    #     return send_from_directory(static_subfolder, filename)

    # If not found as a primary static file, it will fall through.
    # Flask will then try to match it against API routes.
    # If no API route matches, Flask will return a 404.
    logger.warning(f"File '{filename}' not found as a primary static file. Checking API routes or will 404.")
    # No explicit return here, let Flask try other routes or 404.
    # This is better than returning index.html for every unknown path if not an SPA.
    return "File not found", 404


# --- API Routes (These should be fine as they are prefixed with /api/) ---
@app.route('/api/search-scholar', methods=['POST'])
def search_google_scholar_route():
    data = request.json
    query = data.get('query')
    max_results = int(data.get('max_results', 10))
    year_low = data.get('year_low')
    year_high = data.get('year_high')

    if not query:
        return jsonify({"error": "Query is required"}), 400
    logger.info(f"Received Google Scholar search request: query='{query}', max_results={max_results}, year_low={year_low}, year_high={year_high}")

    results = []
    try:
        search_args = {'query': query}
        if year_low is not None: search_args['year_low'] = int(year_low)
        if year_high is not None: search_args['year_high'] = int(year_high)
        
        logger.info(f"Calling scholarly.search_pubs with args: {search_args}")
        search_results_gen = scholarly.search_pubs(**search_args)
        
        count = 0
        for item in search_results_gen:
            if count >= max_results: break
    # Inside the loop in search_google_scholar_route:
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
                authors_list = authors_data # It's already a list of strings
            else: # If it's None or some other unexpected type
                authors_list = []


            results.append({
                "id": f"scholar_{item.get('id_scholarcitedby', bib.get('title', f'untitled_{count}'))}",
                "title": bib.get('title', 'N/A'),
                "authors": authors_list, # Use the processed authors_list
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

@app.route('/api/search-pubmed', methods=['POST'])
def search_pubmed_route():
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
                        pub_date_str = year_node.text # Store raw year if not parsable
            
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

@app.route('/api/rank-bm25', methods=['POST'])
def rank_bm25_route():
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


if __name__ == '__main__':
    # For local network deployment, use host='0.0.0.0'
    # Make sure debug is False if exposing to a less trusted network.
    # For initial testing on your machine, host='localhost' or host='127.0.0.1' is fine.
    app.run(debug=True, host='0.0.0.0', port=5001)
    # To access from another device on your network, find your computer's local IP address
    # (e.g., 192.168.1.10) and go to http://192.168.1.10:5001 in the browser on that device.
    # Your firewall might need to allow connections to port 5001.