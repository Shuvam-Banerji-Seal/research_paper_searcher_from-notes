# Design Document

## Overview

This design document outlines the architectural improvements for the Academic AI Paper Search application. The current application is a monolithic Flask application with mixed concerns and code quality issues. The improvements will focus on modularization, performance optimization, robust error handling, and enhanced user experience while maintaining the existing functionality.

## Architecture

### Current Architecture Issues
- Monolithic Flask application with all logic in a single file (4000+ lines)
- Repetitive proxy setup code (hundreds of duplicate comment lines)
- Mixed concerns (API routes, business logic, utility functions)
- Inconsistent error handling
- No proper configuration management
- Missing proper logging structure

### Proposed Architecture

```
paper_search_app/
├── app.py                 # Main Flask application (entry point)
├── config/
│   ├── __init__.py
│   ├── settings.py        # Configuration management
│   └── logging_config.py  # Logging configuration
├── services/
│   ├── __init__.py
│   ├── search_service.py  # Database search orchestration
│   ├── ollama_service.py  # AI/LLM integration
│   ├── file_service.py    # File processing (PDF, OCR)
│   └── proxy_service.py   # Proxy management
├── api/
│   ├── __init__.py
│   ├── search_routes.py   # Search-related endpoints
│   ├── file_routes.py     # File processing endpoints
│   └── ai_routes.py       # AI/Ollama endpoints
├── models/
│   ├── __init__.py
│   ├── paper.py          # Paper data model
│   └── search_result.py  # Search result aggregation
├── utils/
│   ├── __init__.py
│   ├── validators.py     # Input validation
│   ├── formatters.py     # Data formatting utilities
│   └── cache.py          # Simple caching utilities
└── static/               # Frontend files (existing)
```

## Components and Interfaces

### 1. Configuration Management (`config/settings.py`)

**Purpose**: Centralized configuration management with environment variable support

**Interface**:
```python
class Config:
    # Database search settings
    MAX_RESULTS_PER_DB: int
    SEARCH_TIMEOUT: int
    
    # Ollama settings
    OLLAMA_BASE_URL: str
    OLLAMA_DEFAULT_MODEL: str
    OLLAMA_TIMEOUT: int
    
    # File processing settings
    MAX_FILE_SIZE: int
    ALLOWED_FILE_TYPES: list
    
    # Proxy settings
    PROXY_FILE_PATH: str
    USE_PROXIES: bool
    
    @classmethod
    def from_env(cls) -> 'Config'
```

### 2. Search Service (`services/search_service.py`)

**Purpose**: Orchestrates searches across multiple academic databases with concurrent processing

**Interface**:
```python
class SearchService:
    def __init__(self, config: Config)
    
    async def search_all_databases(
        self, 
        query: str, 
        databases: List[str], 
        filters: SearchFilters
    ) -> SearchResults
    
    async def search_arxiv(self, query: str, filters: SearchFilters) -> List[Paper]
    async def search_scholar(self, query: str, filters: SearchFilters) -> List[Paper]
    async def search_pubmed(self, query: str, filters: SearchFilters) -> List[Paper]
    async def search_semantic_scholar(self, query: str, filters: SearchFilters) -> List[Paper]
    
    def deduplicate_results(self, results: List[Paper]) -> List[Paper]
    def rank_results_bm25(self, results: List[Paper], query: str) -> List[Paper]
```

### 3. Ollama Service (`services/ollama_service.py`)

**Purpose**: Handles all AI/LLM interactions with proper error handling and fallbacks

**Interface**:
```python
class OllamaService:
    def __init__(self, config: Config)
    
    async def refine_query(
        self, 
        original_query: str, 
        context: str = None, 
        model: str = None
    ) -> QueryRefinementResult
    
    async def summarize_abstract(
        self, 
        abstract: str, 
        model: str = None
    ) -> SummarizationResult
    
    async def generate_search_queries(
        self, 
        topic: str, 
        context: str = None, 
        num_queries: int = 5
    ) -> List[str]
    
    def is_available(self) -> bool
    def get_available_models(self) -> List[str]
```

### 4. File Service (`services/file_service.py`)

**Purpose**: Handles file upload, processing, and text extraction with progress tracking

**Interface**:
```python
class FileService:
    def __init__(self, config: Config)
    
    async def process_files(
        self, 
        files: List[FileUpload], 
        progress_callback: Callable = None
    ) -> List[ProcessedFile]
    
    async def extract_text_from_pdf(self, file_path: str) -> str
    async def extract_text_from_image(self, file_path: str) -> str
    
    def validate_file(self, file: FileUpload) -> ValidationResult
    def get_file_info(self, file: FileUpload) -> FileInfo
```

### 5. Proxy Service (`services/proxy_service.py`)

**Purpose**: Clean proxy management without repetitive code

**Interface**:
```python
class ProxyService:
    def __init__(self, config: Config)
    
    def load_proxies(self) -> List[ProxyConfig]
    def get_random_proxy(self) -> Optional[ProxyConfig]
    def setup_scholarly_proxy(self) -> bool
    def test_proxy(self, proxy: ProxyConfig) -> bool
    def rotate_proxy(self) -> bool
```

## Data Models

### Paper Model (`models/paper.py`)

```python
@dataclass
class Paper:
    title: str
    authors: List[str]
    abstract: str
    url: str
    pdf_url: Optional[str]
    published_date: Optional[datetime]
    citations: Optional[int]
    source: str
    doi: Optional[str]
    keywords: List[str]
    bm25_score: Optional[float]
    ai_summary: Optional[str]
    
    def to_dict(self) -> dict
    def to_bibtex(self) -> str
    @classmethod
    def from_dict(cls, data: dict) -> 'Paper'
```

### Search Result Model (`models/search_result.py`)

```python
@dataclass
class SearchResults:
    papers: List[Paper]
    total_count: int
    search_time: float
    databases_searched: List[str]
    query_used: str
    filters_applied: SearchFilters
    
    def sort_by(self, criteria: str) -> 'SearchResults'
    def paginate(self, page: int, per_page: int) -> 'SearchResults'
    def get_statistics(self) -> SearchStatistics
```

## Error Handling

### Error Hierarchy

```python
class PaperSearchError(Exception):
    """Base exception for paper search application"""
    pass

class DatabaseSearchError(PaperSearchError):
    """Raised when database search fails"""
    def __init__(self, database: str, message: str, original_error: Exception = None)

class FileProcessingError(PaperSearchError):
    """Raised when file processing fails"""
    pass

class OllamaServiceError(PaperSearchError):
    """Raised when Ollama service fails"""
    pass

class ConfigurationError(PaperSearchError):
    """Raised when configuration is invalid"""
    pass
```

### Error Response Format

```python
@dataclass
class ErrorResponse:
    error_type: str
    message: str
    details: Optional[dict]
    timestamp: datetime
    request_id: str
    
    def to_dict(self) -> dict
```

### Error Handling Strategy

1. **Graceful Degradation**: If one database fails, continue with others
2. **Fallback Mechanisms**: If AI features fail, provide basic functionality
3. **User-Friendly Messages**: Convert technical errors to actionable user messages
4. **Comprehensive Logging**: Log all errors with context for debugging
5. **Retry Logic**: Implement exponential backoff for transient failures

## Testing Strategy

### Unit Tests
- Test each service class independently
- Mock external dependencies (Ollama, databases)
- Test error conditions and edge cases
- Validate data models and transformations

### Integration Tests
- Test API endpoints end-to-end
- Test file upload and processing workflows
- Test search orchestration across databases
- Test AI integration with real Ollama instance

### Performance Tests
- Load testing for concurrent searches
- File processing performance with large files
- Memory usage during bulk operations
- Response time benchmarks

## Performance Optimizations

### 1. Concurrent Processing
- Use `asyncio` for concurrent database searches
- Parallel file processing for multiple uploads
- Non-blocking AI service calls

### 2. Caching Strategy
```python
class CacheService:
    def cache_search_results(self, query: str, results: SearchResults, ttl: int = 3600)
    def get_cached_results(self, query: str) -> Optional[SearchResults]
    def cache_file_processing(self, file_hash: str, extracted_text: str)
    def get_cached_file_text(self, file_hash: str) -> Optional[str]
```

### 3. Database Connection Pooling
- Implement connection pooling for external API calls
- Rate limiting to respect API quotas
- Circuit breaker pattern for failing services

### 4. Frontend Optimizations
- Implement result pagination
- Progressive loading of search results
- Debounced search input
- Client-side caching of UI state

## Security Considerations

### Input Validation
- Sanitize all user inputs
- Validate file uploads (type, size, content)
- Rate limiting on API endpoints
- CSRF protection for state-changing operations

### Data Privacy
- No persistent storage of user data
- Secure handling of uploaded files
- Clear data retention policies
- Audit logging for sensitive operations

### External Service Security
- Secure proxy configuration
- API key management
- Timeout configurations to prevent hanging requests
- Input sanitization for AI prompts

## Deployment and Configuration

### Environment Variables
```bash
# Database Search
MAX_RESULTS_PER_DB=20
SEARCH_TIMEOUT=30

# Ollama Configuration
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_DEFAULT_MODEL=gemma:3b
OLLAMA_TIMEOUT=60

# File Processing
MAX_FILE_SIZE=50MB
UPLOAD_FOLDER=/tmp/uploads

# Proxy Configuration
PROXY_FILE_PATH=proxies.txt
USE_PROXIES=true

# Logging
LOG_LEVEL=INFO
LOG_FILE=app.log
```

### Docker Configuration
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 5000

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
```

## Migration Strategy

### Phase 1: Code Cleanup and Modularization
1. Remove repetitive proxy code
2. Extract services from main app.py
3. Implement proper configuration management
4. Add comprehensive error handling

### Phase 2: Performance Improvements
1. Implement async search processing
2. Add caching layer
3. Optimize file processing
4. Add progress tracking

### Phase 3: Enhanced Features
1. Improve AI integration
2. Add advanced search filters
3. Implement result deduplication
4. Add export enhancements

### Phase 4: Testing and Documentation
1. Add comprehensive test suite
2. Performance benchmarking
3. API documentation
4. Deployment guides