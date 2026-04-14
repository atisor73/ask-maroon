const API_BASE_URL = "http://127.0.0.1:8000";

const searchForm = document.querySelector("#search-form");
const queryInput = document.querySelector("#query-input");
const backendSelect = document.querySelector("#backend-select");
const limitInput = document.querySelector("#limit-input");
const resultsList = document.querySelector("#results-list");
const statusText = document.querySelector("#status-text");
const viewerTitle = document.querySelector("#viewer-title");
const viewerSubtitle = document.querySelector("#viewer-subtitle");
const openPdfLink = document.querySelector("#open-pdf-link");
const pdfFrame = document.querySelector("#pdf-frame");
const toggleViewerButton = document.querySelector("#toggle-viewer-button");
const randomIssueButton = document.querySelector("#random-issue-button");

let selectedCard = null;
let selectedDocId = null;
let viewerExpanded = false;

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
  setStatus(message);
}

function updateViewerMode() {
  document.body.classList.toggle("pdf-focus-mode", viewerExpanded);
  toggleViewerButton.textContent = viewerExpanded ? "Collapse PDF" : "Expand PDF";
}

function ensureViewerExpanded() {
  if (!viewerExpanded) {
    viewerExpanded = true;
    updateViewerMode();
  }
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
  const fullTextHtml = escapeHtml(bestChunk?.text || "");

  article.innerHTML = `
    <p class="result-kicker">${date} • ${documentResult.doc_id}</p>
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
        doc score: ${documentResult.doc_score.toFixed(3)} • best chunk: ${documentResult.best_chunk_score.toFixed(3)}
      </span>
      <button type="button">Open PDF</button>
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

function openPdf(documentResult) {
  if (selectedDocId === documentResult.doc_id) {
    return;
  }

  // For now we open the issue PDF inline in the right-hand frame.
  // The backend route now serves it with Content-Disposition: inline.
  const pdfUrl = `${API_BASE_URL}/pdf/${encodeURIComponent(documentResult.doc_id)}`;
  selectedDocId = documentResult.doc_id;
  viewerTitle.textContent = documentResult.title || documentResult.doc_id;
  viewerSubtitle.textContent = `${documentResult.date || "Unknown date"} • ${documentResult.doc_id}`;
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
    resultsList.innerHTML = "";
    selectedDocId = null;

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

    data.document_results.forEach((documentResult, index) => {
      const card = buildResultCard(documentResult);
      resultsList.appendChild(card);

      // Auto-open the top result so the PDF pane is not empty after a search.
      if (index === 0) {
        setSelectedCard(card);
        openPdf(documentResult);
      }
    });
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
