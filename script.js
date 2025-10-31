// script.js (Partial - showing key modifications and new functions)
// Assume DOMElements, API_CONFIGS, utility functions like showMessage, setLoading are defined as before.
 
        // --- Polyfills and Setup ---
        if (typeof pdfjsLib !== 'undefined') {
            pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
        } else {
            console.error("pdf.js library is not loaded!");
        }

        // --- Global Variables & Constants ---
        const API_CONFIGS = {
            openrouter: {
                baseUrl: 'https://openrouter.ai/api/v1',
                models: [
                    'anthropic/claude-3.5-sonnet', 'openai/gpt-4o', 'openai/gpt-4-turbo', 'google/gemini-flash-1.5','meta-llama/llama-3-70b-instruct',
                    'mistralai/mixtral-8x7b-instruct','anthropic/claude-3-haiku', 'google/gemini-pro', 
                ]
            },
            groq: {
                baseUrl: 'https://api.groq.com/openai/v1', // Groq uses OpenAI compatible API
                models: ['llama3-70b-8192', 'llama3-8b-8192', 'mixtral-8x7b-32768', 'gemma-7b-it']
            }
        };

        const BACKEND_URL = ''; // Empty string for relative URLs (same origin as frontend)

        let uploadedFilesData = []; // Stores { name: string, text: string }
        let currentSearchResults = [];
        let currentSortCriteria = 'relevance';
        let tesseractWorker = null;


        // --- DOM Elements ---
        const DOMElements = {
            apiProviderSelect: document.getElementById('apiProvider'),
            modelSelect: document.getElementById('model'),
            apiKeyInput: document.getElementById('apiKey'),
            maxResultsSelect: document.getElementById('maxResults'),
            aiSearchToggle: document.getElementById('aiSearch'),
            // autoTranslateToggle: document.getElementById('autoTranslate'), // Placeholder
            databaseCheckboxes: document.querySelectorAll('.database-option input[type="checkbox"]'),
            databaseOptions: document.querySelectorAll('.database-option'),

            fileUploadArea: document.getElementById('fileUploadArea'),
            fileInput: document.getElementById('fileInput'),
            uploadedFilesContainer: document.getElementById('uploadedFilesContainer'),
            notesTextarea: document.getElementById('notes'),

            yearRangeSelect: document.getElementById('yearRange'),
            subjectSelect: document.getElementById('subject'),
            paperTypeSelect: document.getElementById('paperType'),

            searchInput: document.getElementById('searchInput'),
            searchBtn: document.getElementById('searchBtn'),
            generatedQueriesContainer: document.getElementById('generatedQueriesContainer'),
            queryTagsContainer: document.getElementById('queryTagsContainer'),

            statsDashboardContainer: document.getElementById('statsDashboardContainer'),
            totalResultsStat: document.getElementById('totalResultsStat'),
            avgYearStat: document.getElementById('avgYearStat'),
            databaseCountStat: document.getElementById('databaseCountStat'),
            citationCountStat: document.getElementById('citationCountStat'),

            resultsHeaderContainer: document.getElementById('resultsHeaderContainer'),
            resultsContainer: document.getElementById('resultsContainer'),
            sortBtns: document.querySelectorAll('.sort-btn'),

            exportSectionContainer: document.getElementById('exportSectionContainer'),
            exportJsonBtn: document.getElementById('exportJsonBtn'),
            exportCsvBtn: document.getElementById('exportCsvBtn'),
            exportBibtexBtn: document.getElementById('exportBibtexBtn'),
            exportPdfBtn: document.getElementById('exportPdfBtn'),

            themeToggleBtn: document.getElementById('themeToggle'),
            loadingOverlay: document.getElementById('loadingOverlay'),
            loadingText: document.getElementById('loadingText'),
            messageContainer: document.getElementById('messageContainer'),
        };

        // --- Utility Functions ---
        function showMessage(type, message, duration = 5000) {
            const messageDiv = document.createElement('div');
            messageDiv.className = `message ${type}`;
            messageDiv.textContent = message;
            DOMElements.messageContainer.appendChild(messageDiv);
            setTimeout(() => {
                messageDiv.style.opacity = '0';
                messageDiv.style.transform = 'translateY(-20px) translateX(-50%)'; // Slide up
                setTimeout(() => messageDiv.remove(), 500);
            }, duration);
        }

        function setLoading(isLoading, text = "Processing...") {
            DOMElements.loadingOverlay.style.display = isLoading ? 'flex' : 'none';
            DOMElements.loadingText.textContent = text;
            DOMElements.searchBtn.disabled = isLoading;
        }

        async function initializeTesseractWorker() {
            if (!tesseractWorker && typeof Tesseract !== 'undefined') {
                setLoading(true, "Initializing OCR Engine...");
                try {
                    tesseractWorker = await Tesseract.createWorker('eng', 1, {
                        logger: m => console.log(m) // Optional: for progress logging
                    });
                    showMessage('info', 'OCR engine initialized.', 2000);
                } catch (error) {
                    console.error("Error initializing Tesseract worker:", error);
                    showMessage('error', 'Failed to initialize OCR engine.');
                    tesseractWorker = null; // Ensure it's null if failed
                } finally {
                    setLoading(false);
                }
            } else if (typeof Tesseract === 'undefined') {
                 console.error("Tesseract.js library is not loaded!");
                 showMessage('error', 'OCR library (Tesseract.js) not found.');
            }
        }


        // --- Initialization and Event Listeners ---
        document.addEventListener('DOMContentLoaded', () => {
            updateModelDropdown();
            initializeTesseractWorker(); // Initialize Tesseract on load

            DOMElements.apiProviderSelect.addEventListener('change', updateModelDropdown);
            DOMElements.searchBtn.addEventListener('click', handleSearch);
            
            DOMElements.fileUploadArea.addEventListener('click', () => DOMElements.fileInput.click());
            DOMElements.fileInput.addEventListener('change', (e) => handleFiles(e.target.files));

            ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
                DOMElements.fileUploadArea.addEventListener(eventName, preventDefaults, false);
                document.body.addEventListener(eventName, preventDefaults, false); // Prevent browser opening file
            });
            ['dragenter', 'dragover'].forEach(eventName => {
                DOMElements.fileUploadArea.addEventListener(eventName, () => DOMElements.fileUploadArea.classList.add('dragover'), false);
            });
            ['dragleave', 'drop'].forEach(eventName => {
                DOMElements.fileUploadArea.addEventListener(eventName, () => DOMElements.fileUploadArea.classList.remove('dragover'), false);
            });
            DOMElements.fileUploadArea.addEventListener('drop', handleDrop, false);

            DOMElements.sortBtns.forEach(btn => {
                btn.addEventListener('click', () => {
                    DOMElements.sortBtns.forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    currentSortCriteria = btn.dataset.sort;
                    sortAndRenderResults();
                });
            });

            DOMElements.exportJsonBtn.addEventListener('click', () => exportResults('json'));
            DOMElements.exportCsvBtn.addEventListener('click', () => exportResults('csv'));
            DOMElements.exportBibtexBtn.addEventListener('click', () => exportResults('bibtex'));
            DOMElements.exportPdfBtn.addEventListener('click', () => exportResults('pdf'));

            DOMElements.themeToggleBtn.addEventListener('click', toggleTheme);
            if (localStorage.getItem('theme') === 'dark-theme') {
                document.body.classList.add('dark-theme');
                DOMElements.themeToggleBtn.textContent = '☀️';
            }

            DOMElements.databaseOptions.forEach(option => {
                const checkbox = option.querySelector('input[type="checkbox"]');
                option.addEventListener('click', (e) => {
                    if (e.target !== checkbox) { // Prevent double toggle if label is clicked
                        checkbox.checked = !checkbox.checked;
                    }
                    option.classList.toggle('selected', checkbox.checked);
                });
            });
        });

        function preventDefaults(e) {
            e.preventDefault();
            e.stopPropagation();
        }

        function handleDrop(e) {
            let dt = e.dataTransfer;
            let files = dt.files;
            handleFiles(files);
        }

        function updateModelDropdown() {
            const provider = DOMElements.apiProviderSelect.value;
            const models = API_CONFIGS[provider].models;
            DOMElements.modelSelect.innerHTML = models.map(model => `<option value="${model}">${model}</option>`).join('');
        }

        // --- File Handling and OCR ---
        async function handleFiles(files) {
            if (!files.length) return;
            setLoading(true, "Processing files...");

            for (const file of files) {
                if (uploadedFilesData.find(f => f.name === file.name)) {
                    showMessage('info', `File ${file.name} already uploaded.`);
                    continue;
                }
                let text = '';
                try {
                    if (file.type === "application/pdf") {
                        text = await extractTextFromPdf(file);
                    } else if (file.type.startsWith("image/")) {
                        if (!tesseractWorker) {
                           await initializeTesseractWorker(); // try to init again if not ready
                           if (!tesseractWorker) { // if still not ready, skip OCR
                                showMessage('error', 'OCR Engine not ready. Cannot process image.');
                                continue;
                           }
                        }
                        text = await extractTextFromImage(file);
                    } else {
                        showMessage('error', `Unsupported file type: ${file.name}`);
                        continue;
                    }
                    uploadedFilesData.push({ name: file.name, text: text });
                    renderUploadedFiles();
                    showMessage('success', `Processed: ${file.name}`);
                } catch (error) {
                    console.error("Error processing file:", file.name, error);
                    showMessage('error', `Error processing ${file.name}: ${error.message}`);
                }
            }
            setLoading(false);
        }

        async function extractTextFromPdf(file) {
            const arrayBuffer = await file.arrayBuffer();
            const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;
            let fullText = '';
            for (let i = 1; i <= pdf.numPages; i++) {
                const page = await pdf.getPage(i);
                const textContent = await page.getTextContent();
                fullText += textContent.items.map(item => item.str).join(' ') + '\n';
            }
            return fullText;
        }

        async function extractTextFromImage(file) {
            if (!tesseractWorker) {
                throw new Error("Tesseract worker not initialized.");
            }
            const { data: { text } } = await tesseractWorker.recognize(file);
            return text;
        }

        function renderUploadedFiles() {
            DOMElements.uploadedFilesContainer.innerHTML = uploadedFilesData.map((file, index) => `
                <div class="file-tag">
                    ${file.name}
                    <span class="remove" data-index="${index}" title="Remove file">×</span>
                </div>
            `).join('');

            DOMElements.uploadedFilesContainer.querySelectorAll('.remove').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    const index = parseInt(e.target.dataset.index);
                    uploadedFilesData.splice(index, 1);
                    renderUploadedFiles();
                });
            });
        }

// --- LLM Query Generation (Modified to use Ollama backend) ---
async function generateLLMQueries(mainTopic, notes, fileTextContent) {
    const model = 'gemma:3b'; // User specified model
    // No API Key needed for local Ollama via backend

    let context = `User's main topic/question: "${mainTopic}"\n`;
    if (notes) context += `Additional notes/context from user: "${notes}"\n`;
    if (fileTextContent) context += `Key content extracted from uploaded documents (e.g., lecture notes, paper excerpts, book pages):\n---\n${fileTextContent.substring(0, 4000)}\n---\n`;

    const subject = DOMElements.subjectSelect.value;
    const paperType = DOMElements.paperTypeSelect.value;
    
    let subjectHint = "";
    if (subject && subject !== 'all') {
        subjectHint = `The user is particularly interested in the academic subject area of: ${subject}. `;
        if (subject.toLowerCase().includes('math')) {
            subjectHint += `For ArXiv, relevant categories might be 'math.XX' (e.g., 'math.NT' for Number Theory, 'math.CO' for Combinatorics), 'stat.TH' (Statistics Theory), etc. Queries can use 'cat:math.XX AND (term OR term)'. `;
        } else if (subject.toLowerCase().includes('cs') || subject.toLowerCase().includes('computer science')) {
             subjectHint += `For ArXiv, relevant categories might be 'cs.XX' (e.g., 'cs.AI' for AI, 'cs.LG' for Machine Learning). `;
        }
    }
    let paperTypeHint = "";
    if (paperType && paperType !== 'all') {
        paperTypeHint = `The user is looking for papers that are primarily of type: ${paperType}. `;
    }

    const prompt = `
You are an expert research assistant. Your task is to generate highly effective search queries for academic databases like ArXiv and Google Scholar, based on the user's input.
The user's input might include a main topic, additional notes, and text extracted from documents (like lecture notes, research papers, or book pages).

User-provided information:
${context}

Specific interests:
${subjectHint}
${paperTypeHint}

Instructions:
1.  Analyze all the provided information to understand the core research area, key concepts, specific problems, relevant mathematical formalisms or algorithms (if any), and potentially important authors or seminal works mentioned.
2.  Generate 3-5 DIVERSE and PRECISE search queries. These queries should be what an expert researcher would type into a search bar.
3.  For ArXiv:
    *   Utilize field codes where appropriate (e.g., 'ti:(title terms)', 'au:(author name)', 'abs:(abstract terms)', 'cat:(category e.g., math.NT or cs.AI)').
    *   Combine terms using boolean operators (AND, OR, NOT). Example: "cat:math.PR AND ti:(stochastic processes) AND (markov chains OR random walks)"
4.  For Google Scholar (and general academic search):
    *   Use boolean operators (AND, OR, NOT).
    *   Use exact phrases with double quotes (e.g., "deep learning for theorem proving").
    *   Consider using operators like 'author:"J Doe"' or 'source:"Nature"'.
5.  If the input text is complex (e.g., from a research paper), try to extract specific terminology, method names, or unique phrases that would be good search terms.
6.  Focus on precision. Avoid overly broad queries.
7.  The queries should be optimized for mathematical papers if the context or subject strongly suggests it.

Output Format:
Return ONLY a JSON array of strings, where each string is a distinct search query. Do not include any other text or explanations.
Example: ["ti:(quantum field theory) AND cat:hep-th", "gravitational waves ligo virgo", "author:\\"Witten E\\" string theory"]
`;

    setLoading(true, "Generating AI search queries...");
    try {
        const response = await fetch(`${BACKEND_URL}/api/ollama-refine-query`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query: prompt, // Send the full prompt to the backend
                model: model
            })
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(`Ollama Query Refinement API Error (${response.status}): ${errorData.error || response.statusText}`);
        }

        const data = await response.json();
        const refinedQuery = data.refined_query; // This is expected to be the JSON string of queries

        if (refinedQuery) {
            try {
                let queries = JSON.parse(refinedQuery);
                if (Array.isArray(queries) && queries.every(q => typeof q === 'string')) {
                    showMessage('success', 'AI search queries generated.');
                    return queries;
                }
            } catch (e) {
                console.warn("Ollama response was not perfect JSON, attempting regex extraction:", e);
                const queryRegex = /"([^"]+)"/g;
                let matches;
                const extractedQueries = [];
                while ((matches = queryRegex.exec(refinedQuery)) !== null) {
                    if (matches[1].trim().length > 3) {
                       extractedQueries.push(matches[1].trim());
                    }
                }
                if (extractedQueries.length > 0) {
                    showMessage('success', `AI queries generated (extracted ${extractedQueries.length}).`);
                    return extractedQueries;
                }
            }
        }
        throw new Error("Ollama did not return valid queries.");

    } catch (error) {
        console.error("Error generating LLM queries:", error);
        showMessage('error', `Failed to generate AI queries: ${error.message}`);
        return [];
    } finally {
        setLoading(false);
    }
}


// --- LLM Verbose Query Generation for BM25 (Modified to use Ollama backend) ---
async function generateBM25VerboseQuery(mainTopic, notes, fileTextContent) {
    const model = 'gemma:3b'; // User specified model
    // No API Key needed for local Ollama via backend

    let context = `User's main topic/question: "${mainTopic}"\n`;
    if (notes) context += `Additional notes/context from user: "${notes}"\n`;
    if (fileTextContent) context += `Key content extracted from uploaded documents:\n---\n${fileTextContent.substring(0, 5000)}\n---\n`;

    const subject = DOMElements.subjectSelect.value;
    let subjectHint = subject && subject !== 'all' ? `The user's primary subject focus is: ${subject}. ` : "";

    const prompt = `
You are an expert research analyst. Your task is to generate a **single, detailed, verbose paragraph**. This paragraph should synthesize all the provided user input (topic, notes, document excerpts) into a rich description of the ideal research paper or information the user is seeking.

User-provided information:
${context}
${subjectHint}

Instructions:
1.  Read and understand all the provided context.
2.  DO NOT generate search queries.
3.  Instead, write a coherent paragraph (around 100-250 words) that elaborates on the key concepts, research questions, methodologies, specific terminology, and desired outcomes or information.
4.  This paragraph will be used by a BM25 relevance scoring algorithm to compare against the abstracts of retrieved papers. Therefore, it should be rich in relevant keywords, phrases, and conceptual descriptions.
5.  If the input mentions mathematical concepts, try to incorporate them descriptively.
6.  The paragraph should sound like a human describing their precise research interest in detail.

Output:
Return ONLY the single descriptive paragraph as a plain text string. Do not include any other text, titles, or formatting.
`;

    setLoading(true, "Generating AI verbose query for BM25...");
    try {
        const response = await fetch(`${BACKEND_URL}/api/ollama-refine-query`, { // Reusing refine-query endpoint for simplicity, but prompt is different
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query: prompt, // Send the full prompt
                model: model
            })
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(`Ollama BM25 Query Generation API Error (${response.status}): ${errorData.error || response.statusText}`);
        }
        const data = await response.json();
        const verboseQuery = data.refined_query; // Expecting the paragraph here
        if (verboseQuery) {
            showMessage('success', 'AI verbose query for BM25 generated.');
            currentVerboseBM25Query = verboseQuery;
            return verboseQuery;
        }
        throw new Error("Ollama did not return a valid verbose query.");
    } catch (error) {
        console.error("Error generating BM25 verbose query:", error);
        showMessage('error', `Failed to generate AI verbose query for BM25: ${error.message}`);
        currentVerboseBM25Query = "";
        return null;
    } finally {
        setLoading(false);
    }
}


// --- Abstract Summarization (New Function) ---
async function summarizeAbstractWithOllama(abstract) {
    const model = 'gemma:3b'; // User specified model
    if (!abstract) return "No abstract to summarize.";

    setLoading(true, "Summarizing abstract with AI...");
    try {
        const response = await fetch(`${BACKEND_URL}/api/ollama-summarize-abstract`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                abstract: abstract,
                model: model
            })
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(`Ollama Abstract Summarization API Error (${response.status}): ${errorData.error || response.statusText}`);
        }

        const data = await response.json();
        const summary = data.summary;
        if (summary) {
            showMessage('success', 'Abstract summarized by AI.');
            return summary;
        }
        throw new Error("Ollama did not return a valid summary.");
    } catch (error) {
        console.error("Error summarizing abstract:", error);
        showMessage('error', `Failed to summarize abstract: ${error.message}`);
        return abstract.substring(0, 300) + (abstract.length > 300 ? '...' : ''); // Fallback to truncated original
    } finally {
        setLoading(false);
    }
}


// --- Results Rendering (Modified to include AI summary) ---
async function renderResults(results) {
    if (!results || results.length === 0) {
         DOMElements.resultsContainer.innerHTML = `<p class="message info" style="text-align:center; display:block; opacity:1; transform:none;">No papers found matching your criteria.</p>`;
         DOMElements.resultsHeaderContainer.style.display = 'none';
         DOMElements.exportSectionContainer.style.display = 'none';
         return;
    }

    // Process abstracts with Ollama for summarization
    const papersWithSummaries = await Promise.all(results.map(async paper => {
        if (paper.abstract && paper.abstract.length > 50) { // Only summarize if abstract exists and is reasonably long
            const summary = await summarizeAbstractWithOllama(paper.abstract);
            return { ...paper, aiSummary: summary };
        }
        return { ...paper, aiSummary: paper.abstract }; // Use original abstract if no summary generated
    }));

    DOMElements.resultsContainer.innerHTML = papersWithSummaries.map(paper => `
        <div class="paper-card">
            <div class="paper-header">
                <h4 class="paper-title"><a href="${paper.url}" target="_blank" rel="noopener noreferrer">${paper.title}</a></h4>
                <span class="paper-source">${paper.source}</span>
            </div>
            <p class="paper-authors">Authors: ${paper.authors?.join(', ') || 'N/A'}</p>
            <div class="paper-abstract">
                ${paper.aiSummary ? paper.aiSummary.substring(0, 300) + (paper.aiSummary.length > 300 ? '...' : '') : 'No abstract available.'}
            </div>
            ${paper.aiSummary && paper.aiSummary.length > 300 ? '<span class="abstract-toggle">Read more</span>' : ''}
            <div class="paper-meta">
                <span>Published: ${paper.publishedDate ? new Date(paper.publishedDate).toLocaleDateString() : 'N/A'}</span>
                <span>Citations: ${paper.citations !== null ? paper.citations : 'N/A'}</span>
                <div class="paper-actions">
                    ${paper.pdfUrl ? `<a href="${paper.pdfUrl}" class="action-btn" target="_blank" rel="noopener noreferrer">PDF</a>` : ''}
                    <a href="${paper.url}" class="action-btn" target="_blank" rel="noopener noreferrer">Source Page</a>
                </div>
            </div>
        </div>
    `).join('');
    
    // Add event listeners for "Read more" toggles
    DOMElements.resultsContainer.querySelectorAll('.abstract-toggle').forEach((toggle, index) => {
        toggle.addEventListener('click', () => {
            const abstractDiv = toggle.previousElementSibling; // The .paper-abstract div
            abstractDiv.classList.toggle('expanded');
            if (abstractDiv.classList.contains('expanded')) {
                abstractDiv.textContent = papersWithSummaries[index].aiSummary; // Show full AI summary
                toggle.textContent = 'Read less';
            } else {
                abstractDiv.textContent = papersWithSummaries[index].aiSummary.substring(0, 300) + '...';
                toggle.textContent = 'Read more';
            }
        });
    });
}
