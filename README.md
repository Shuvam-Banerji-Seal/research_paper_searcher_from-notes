# Academic AI Paper Search

An intelligent research paper discovery tool that searches across multiple academic databases with AI-powered query generation and ranking.

## Features

- **Multi-Database Search**: Search across:
  - PubMed (biomedical literature)
  - Google Scholar (broad academic coverage)
  - arXiv (preprints and open access)
  - Semantic Scholar (AI-powered academic search)
  - CrossRef (DOI and citation data)

- **AI-Powered Features**:
  - Query refinement using Ollama AI
  - Abstract summarization
  - BM25 ranking for relevance scoring

- **Advanced Filtering**:
  - Year range filtering
  - Subject area filtering
  - Paper type filtering

- **Document Upload**:
  - PDF text extraction
  - Image OCR with Tesseract
  - Notes integration for context-aware searches

## Installation

### Prerequisites

- Python 3.8 or higher
- Ollama (optional, for AI features)

### Setup

1. Clone the repository:
```bash
git clone https://github.com/Shuvam-Banerji-Seal/research_paper_searcher_from-notes.git
cd research_paper_searcher_from-notes
```

2. Install Python dependencies:
```bash
pip install -r requirements.txt
```

3. Download NLTK data (automatically done on first run):
```python
import nltk
nltk.download('punkt')
```

4. (Optional) Install Ollama for AI features:
- Visit [Ollama](https://ollama.ai) for installation instructions
- Pull a model: `ollama pull gemma:2b`

## Usage

### Starting the Server

Run the Flask server:
```bash
python app.py
```

The application will be available at `http://localhost:5001`

### Using the Web Interface

1. **Configure Search**:
   - Select databases to search
   - Set maximum results per database
   - Enable AI-powered query refinement (optional)

2. **Upload Documents** (optional):
   - Drag and drop PDFs or images
   - Add notes for context

3. **Search**:
   - Enter your search query
   - Apply filters (year range, subject, paper type)
   - Click "Search Papers"

4. **View Results**:
   - Browse sorted results by relevance
   - View abstracts and metadata
   - Access full papers via provided links
   - Export results to CSV

## API Endpoints

### Search Endpoints

- `POST /api/search-pubmed` - Search PubMed
- `POST /api/search-scholar` - Search Google Scholar
- `POST /api/search-arxiv` - Search arXiv
- `POST /api/search-semantic-scholar` - Search Semantic Scholar
- `POST /api/search-crossref` - Search CrossRef

### Utility Endpoints

- `POST /api/rank-bm25` - Rank papers using BM25 algorithm
- `POST /api/ollama-refine-query` - Refine query with AI
- `POST /api/ollama-summarize-abstract` - Summarize abstract with AI

## Configuration

### API Keys

Some features may require API keys:
- OpenRouter / Groq: For advanced AI features (configure in the web interface)
- Note: Basic search functionality works without API keys

### Proxies (Optional)

For Google Scholar search with proxies:
1. Create a `proxies.txt` file in the root directory
2. Add proxy URLs (one per line):
```
http://proxy1.example.com:8080
http://proxy2.example.com:8080
```

## Technology Stack

- **Backend**: Flask, Python
- **Frontend**: HTML, CSS, JavaScript
- **Search Libraries**: 
  - scholarly (Google Scholar)
  - requests (HTTP APIs)
  - rank_bm25 (ranking algorithm)
- **AI Integration**: Ollama
- **Document Processing**: 
  - pdf.js (PDF rendering)
  - Tesseract.js (OCR)

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is open source and available under the MIT License.

## Author

Created by Shuvam Banerji Seal

## Acknowledgments

- Thanks to all the open-source projects and APIs that make this tool possible
- Google Scholar, PubMed, arXiv, Semantic Scholar, and CrossRef for providing academic data
