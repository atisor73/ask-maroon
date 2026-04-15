const API_BASE_URL = "http://127.0.0.1:8000";

const searchForm = document.querySelector("#search-form");
const queryInput = document.querySelector("#query-input");
const backendSelect = document.querySelector("#backend-select");
const limitInput = document.querySelector("#limit-input");
const resultsList = document.querySelector("#results-list");
const statusText = document.querySelector("#status-text");
const paginationBar = document.querySelector("#pagination-bar");
const paginationText = document.querySelector("#pagination-text");
const prevPageButton = document.querySelector("#prev-page-button");
const nextPageButton = document.querySelector("#next-page-button");
const viewerTitle = document.querySelector("#viewer-title");
const viewerSubtitle = document.querySelector("#viewer-subtitle");
const openPdfLink = document.querySelector("#open-pdf-link");
const pdfFrame = document.querySelector("#pdf-frame");
const toggleViewerButton = document.querySelector("#toggle-viewer-button");
const randomIssueButton = document.querySelector("#random-issue-button");
const collapseViewerEdge = document.querySelector("#collapse-viewer-edge");

let selectedCard = null;
let selectedDocId = null;
let selectedPageNumber = null;
let viewerExpanded = false;
let currentResults = [];
let currentPage = 1;
const RESULTS_PER_PAGE = 10;

function setStatus(message) {
  statusText.textContent = message;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function renderEmptyState(message) {
  resultsList.innerHTML = "";
  currentResults = [];
  currentPage = 1;
  paginationBar.hidden = true;
  setStatus(message);
}

function updateViewerMode() {
  document.body.classList.toggle("pdf-focus-mode", viewerExpanded);
  toggleViewerButton.textContent = viewerExpanded ? "Collapse PDF-Viewer" : "Expand PDF-Viewer";
}

function ensureViewerExpanded() {
  if (!viewerExpanded) {
    viewerExpanded = true;
    updateViewerMode();
  }
}

function preferredPage(documentResult) {
  if (!documentResult?.chunks?.length) {
    return null;
  }

  const bestChunk =
    documentResult.chunks.find((chunk) => chunk.chunk_id === documentResult.best_chunk_id) ||
    documentResult.chunks[0];

  return bestChunk?.page_number || null;
}

function buildResultCard(documentResult) {
  const article = document.createElement("article");
  article.className = "result-card";

  // We use the document's best-ranked chunk for the preview in this MVP UI.
  const bestChunk =
    documentResult.chunks.find((chunk) => chunk.chunk_id === documentResult.best_chunk_id) ||
    documentResult.chunks[0];

  const title = documentResult.title || documentResult.doc_id;
  const date = documentResult.date || "Unknown date";
  const snippetHtml = bestChunk?.snippet_html || escapeHtml(bestChunk?.snippet || "");
  const fullTextHtml = bestChunk?.full_text_html || escapeHtml(bestChunk?.text || "");
  const pageLabel = bestChunk?.page_number ? ` • p. ${bestChunk.page_number}` : "";

  article.innerHTML = `
    <p class="result-kicker">${date} • ${documentResult.doc_id}${pageLabel}</p>
    <h3>${escapeHtml(title)}</h3>
    <div class="result-snippet-wrap">
      <p class="result-snippet">${snippetHtml}</p>
      <div class="result-fulltext" hidden>${fullTextHtml}</div>
      <button type="button" class="snippet-toggle" aria-expanded="false" aria-label="Expand result text">
        ▼
      </button>
    </div>
    <div class="result-meta">
      <span>
        doc score: ${documentResult.doc_score.toFixed(3)} • chunk score: ${documentResult.best_chunk_score.toFixed(3)}
      </span>
      <button type="button">View PDF</button>
    </div>
  `;

  const snippetToggle = article.querySelector(".snippet-toggle");
  const snippet = article.querySelector(".result-snippet");
  const fullText = article.querySelector(".result-fulltext");
  const openPdfButton = article.querySelector(".result-meta button");

  snippetToggle.addEventListener("click", (event) => {
    event.stopPropagation();
    const isExpanded = snippetToggle.getAttribute("aria-expanded") === "true";
    snippetToggle.setAttribute("aria-expanded", String(!isExpanded));
    snippetToggle.textContent = isExpanded ? "▼" : "▲";
    snippet.hidden = !isExpanded;
    fullText.hidden = isExpanded;
  });

  openPdfButton.addEventListener("click", (event) => {
    event.stopPropagation();
    setSelectedCard(article);
    openPdf(documentResult);
  });

  article.addEventListener("click", () => {
    setSelectedCard(article);
    openPdf(documentResult);
  });

  return article;
}

function renderPagination() {
  const totalResults = currentResults.length;
  const totalPages = Math.max(1, Math.ceil(totalResults / RESULTS_PER_PAGE));

  if (totalResults <= RESULTS_PER_PAGE) {
    paginationBar.hidden = true;
    return;
  }

  const start = (currentPage - 1) * RESULTS_PER_PAGE + 1;
  const end = Math.min(totalResults, currentPage * RESULTS_PER_PAGE);
  const label = `${start}\u2013${end} of ${totalResults}`;

  paginationBar.hidden = false;
  paginationText.textContent = label;
  prevPageButton.disabled = currentPage <= 1;
  nextPageButton.disabled = currentPage >= totalPages;
}

function renderResultsPage() {
  resultsList.innerHTML = "";
  selectedDocId = null;
  selectedPageNumber = null;
  setSelectedCard(null);

  if (!currentResults.length) {
    renderPagination();
    return;
  }

  const start = (currentPage - 1) * RESULTS_PER_PAGE;
  const end = start + RESULTS_PER_PAGE;
  const pageResults = currentResults.slice(start, end);

  pageResults.forEach((documentResult, index) => {
    const card = buildResultCard(documentResult);
    resultsList.appendChild(card);

    if (index === 0) {
      setSelectedCard(card);
      openPdf(documentResult);
    }
  });

  renderPagination();
}

function openPdf(documentResult) {
  const pageNumber = preferredPage(documentResult);

  if (selectedDocId === documentResult.doc_id && selectedPageNumber === pageNumber) {
    return;
  }

  // For now we open the issue PDF inline in the right-hand frame.
  // The browser PDF viewer often honors #page=N, so we append it when we have one.
  const basePdfUrl = `${API_BASE_URL}/pdf/${encodeURIComponent(documentResult.doc_id)}`;
  const pdfUrl = pageNumber ? `${basePdfUrl}#page=${pageNumber}` : basePdfUrl;
  selectedDocId = documentResult.doc_id;
  selectedPageNumber = pageNumber;
  viewerTitle.textContent = documentResult.title || documentResult.doc_id;
  viewerSubtitle.textContent = pageNumber
    ? `${documentResult.date || "Unknown date"} • Page ${pageNumber}`
    : `${documentResult.date || "Unknown date"}`;
  openPdfLink.href = pdfUrl;
  pdfFrame.src = pdfUrl;
}

function setSelectedCard(cardElement) {
  if (selectedCard) {
    selectedCard.classList.remove("is-selected");
  }

  selectedCard = cardElement;

  if (selectedCard) {
    selectedCard.classList.add("is-selected");
  }
}

async function openRandomIssue() {
  setStatus("Exploring a random issue...");

  try {
    const response = await fetch(`${API_BASE_URL}/random-document`);
    if (!response.ok) {
      throw new Error(`Random issue request failed with status ${response.status}`);
    }

    const documentResult = await response.json();
    setSelectedCard(null);
    selectedDocId = null;
    selectedPageNumber = null;
    ensureViewerExpanded();
    openPdf(documentResult);
    setStatus(
      `Exploring ${documentResult.date || "an undated issue"} • ${documentResult.doc_id}.`
    );
  } catch (error) {
    setStatus(`Random issue failed: ${error.message}`);
  }
}

async function runSearch(event) {
  event.preventDefault();

  const query = queryInput.value.trim();
  if (!query) {
    renderEmptyState("Enter a query first.");
    return;
  }

  const params = new URLSearchParams({
    q: query,
    backend: backendSelect.value,
    limit: limitInput.value,
  });

  setStatus(`Searching for "${query}"...`);
  resultsList.innerHTML = "";

  try {
    const response = await fetch(`${API_BASE_URL}/search?${params.toString()}`);
    if (!response.ok) {
      throw new Error(`Search request failed with status ${response.status}`);
    }

    const data = await response.json();
    if (!data.document_results.length) {
      renderEmptyState(`No results found for "${query}".`);
      return;
    }

    // Tell the user which vector backend actually served the request.
    if (data.used_fallback) {
      setStatus(
        `OpenAI query failed, so the backend fell back to ${data.vector_backend}. Showing ${data.document_results.length} documents.`
      );
    } else {
      setStatus(
        `Showing ${data.document_results.length} documents using ${data.vector_backend}.`
      );
    }

    currentResults = data.document_results;
    currentPage = 1;
    renderResultsPage();
  } catch (error) {
    renderEmptyState(`Search failed: ${error.message}`);
  }
}

searchForm.addEventListener("submit", runSearch);
randomIssueButton.addEventListener("click", openRandomIssue);

toggleViewerButton.addEventListener("click", () => {
  viewerExpanded = !viewerExpanded;
  updateViewerMode();
});

collapseViewerEdge.addEventListener("click", () => {
  viewerExpanded = false;
  updateViewerMode();
});

prevPageButton.addEventListener("click", () => {
  if (currentPage <= 1) {
    return;
  }
  currentPage -= 1;
  renderResultsPage();
});

nextPageButton.addEventListener("click", () => {
  const totalPages = Math.max(1, Math.ceil(currentResults.length / RESULTS_PER_PAGE));
  if (currentPage >= totalPages) {
    return;
  }
  currentPage += 1;
  renderResultsPage();
});
