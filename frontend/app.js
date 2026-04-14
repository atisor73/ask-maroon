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

  article.innerHTML = `
    <p class="result-kicker">${date} • ${documentResult.doc_id}</p>
    <h3>${escapeHtml(title)}</h3>
    <p class="result-snippet">${snippetHtml}</p>
    <div class="result-meta">
      <span>
        doc score: ${documentResult.doc_score.toFixed(3)} • best chunk: ${documentResult.best_chunk_score.toFixed(3)}
      </span>
      <button type="button">Open PDF</button>
    </div>
  `;

  const button = article.querySelector("button");
  button.addEventListener("click", () => openPdf(documentResult));

  return article;
}

function openPdf(documentResult) {
  // For now we open the issue PDF inline in the right-hand frame.
  // The backend route now serves it with Content-Disposition: inline.
  const pdfUrl = `${API_BASE_URL}/pdf/${encodeURIComponent(documentResult.doc_id)}`;
  viewerTitle.textContent = documentResult.title || documentResult.doc_id;
  viewerSubtitle.textContent = `${documentResult.date || "Unknown date"} • ${documentResult.doc_id}`;
  openPdfLink.href = pdfUrl;
  pdfFrame.src = pdfUrl;
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
        openPdf(documentResult);
      }
    });
  } catch (error) {
    renderEmptyState(`Search failed: ${error.message}`);
  }
}

searchForm.addEventListener("submit", runSearch);
