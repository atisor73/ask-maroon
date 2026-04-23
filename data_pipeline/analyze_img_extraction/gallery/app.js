const indexPath = "./data/index.json";
const numberFormatter = new Intl.NumberFormat();

const state = {
  indexData: null,
  activeDecade: null,
  decadeCache: new Map(),
};

const totalImageCount = document.querySelector("#total-image-count");
const generationNote = document.querySelector("#generation-note");
const decadeList = document.querySelector("#decade-list");
const detailTitle = document.querySelector("#detail-title");
const detailSubtitle = document.querySelector("#detail-subtitle");
const yearSections = document.querySelector("#year-sections");
const lightbox = document.querySelector("#lightbox");
const lightboxImage = document.querySelector("#lightbox-image");
const lightboxTitle = document.querySelector("#lightbox-title");
const lightboxCaption = document.querySelector("#lightbox-caption");
const lightboxLink = document.querySelector("#lightbox-link");
const lightboxClose = document.querySelector("#lightbox-close");

async function fetchJson(path) {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`Request failed for ${path}: ${response.status}`);
  }
  return response.json();
}

function formatCount(value) {
  return numberFormatter.format(value || 0);
}

function formatGeneratedAt(value) {
  if (!value) {
    return "";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }

  return `Generated ${date.toLocaleString()}`;
}

function setLoadingState(title, subtitle) {
  detailTitle.textContent = title;
  detailSubtitle.textContent = subtitle;
  yearSections.innerHTML = "";
}

function buildPreviewStrip(items) {
  const strip = document.createElement("div");
  strip.className = "preview-strip";

  items.slice(0, 4).forEach((item) => {
    const img = document.createElement("img");
    img.className = "preview-thumb";
    img.src = item.thumbnail_path;
    img.alt = `${item.label} from ${item.doc_id}`;
    img.loading = "lazy";
    img.addEventListener("error", () => {
      img.src = item.full_image_path;
    });
    strip.appendChild(img);
  });

  return strip;
}

function buildDecadeCard(decadeSummary) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "decade-card";
  button.dataset.decade = decadeSummary.decade;
  button.setAttribute("aria-pressed", String(state.activeDecade === decadeSummary.decade));

  if (state.activeDecade === decadeSummary.decade) {
    button.classList.add("is-active");
  }

  const meta = document.createElement("div");
  meta.className = "decade-meta";

  const title = document.createElement("h3");
  title.textContent = decadeSummary.decade;
  meta.appendChild(title);

  const stats = document.createElement("p");
  stats.textContent = `${formatCount(decadeSummary.image_count)} images across ${decadeSummary.year_count} years`;
  meta.appendChild(stats);

  button.appendChild(meta);
  button.appendChild(buildPreviewStrip(decadeSummary.preview_items || []));
  button.addEventListener("click", () => {
    loadDecade(decadeSummary.decade);
  });

  return button;
}

function renderDecadeList() {
  decadeList.innerHTML = "";
  state.indexData.decades.forEach((decadeSummary) => {
    decadeList.appendChild(buildDecadeCard(decadeSummary));
  });
}

function buildImageButton(item) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "image-card";

  const image = document.createElement("img");
  image.className = "image-card-thumb";
  image.src = item.thumbnail_path;
  image.alt = `${item.label} from ${item.doc_id}`;
  image.loading = "lazy";
  image.addEventListener("error", () => {
    image.src = item.full_image_path;
  });

  const caption = document.createElement("div");
  caption.className = "image-card-caption";

  const title = document.createElement("strong");
  title.textContent = item.doc_id;
  caption.appendChild(title);

  const meta = document.createElement("span");
  const pageLabel = item.page_number ? `page ${item.page_number}` : "page ?";
  meta.textContent = `${item.label} • ${pageLabel}`;
  caption.appendChild(meta);

  button.appendChild(image);
  button.appendChild(caption);
  button.addEventListener("click", () => openLightbox(item));
  return button;
}

function renderYearItems(container, items) {
  container.innerHTML = "";
  const grid = document.createElement("div");
  grid.className = "image-grid";
  items.forEach((item) => {
    grid.appendChild(buildImageButton(item));
  });
  container.appendChild(grid);
}

function buildYearSection(yearPayload) {
  const section = document.createElement("section");
  section.className = "year-section";

  const button = document.createElement("button");
  button.type = "button";
  button.className = "year-toggle";
  button.setAttribute("aria-expanded", "false");

  const heading = document.createElement("div");
  heading.className = "year-heading";

  const title = document.createElement("h3");
  title.textContent = String(yearPayload.year);
  heading.appendChild(title);

  const stats = document.createElement("p");
  stats.textContent = `${formatCount(yearPayload.image_count)} images`;
  heading.appendChild(stats);

  button.appendChild(heading);
  button.appendChild(buildPreviewStrip(yearPayload.preview_items || []));

  const body = document.createElement("div");
  body.className = "year-body";
  body.hidden = true;

  button.addEventListener("click", () => {
    const expanded = button.getAttribute("aria-expanded") === "true";
    button.setAttribute("aria-expanded", String(!expanded));
    body.hidden = expanded;
    section.classList.toggle("is-open", !expanded);
    if (!expanded && !body.hasChildNodes()) {
      renderYearItems(body, yearPayload.items || []);
    }
  });

  section.appendChild(button);
  section.appendChild(body);
  return section;
}

function renderDecadeDetail(decadePayload) {
  detailTitle.textContent = `${decadePayload.decade} image browser`;
  detailSubtitle.textContent = `${formatCount(decadePayload.image_count)} images grouped into ${decadePayload.year_count} years`;
  yearSections.innerHTML = "";

  decadePayload.years.forEach((yearPayload) => {
    yearSections.appendChild(buildYearSection(yearPayload));
  });
}

async function loadDecade(decade) {
  state.activeDecade = decade;
  renderDecadeList();

  const decadeSummary = state.indexData.decades.find((entry) => entry.decade === decade);
  if (!decadeSummary) {
    setLoadingState("Gallery", "Decade not found.");
    return;
  }

  setLoadingState(`${decade} image browser`, "Loading years and thumbnails...");

  try {
    let decadePayload = state.decadeCache.get(decade);
    if (!decadePayload) {
      decadePayload = await fetchJson(`./${decadeSummary.data_path}`);
      state.decadeCache.set(decade, decadePayload);
    }
    renderDecadeDetail(decadePayload);
  } catch (error) {
    setLoadingState(`${decade} image browser`, `Failed to load decade data: ${error.message}`);
  }
}

function openLightbox(item) {
  lightboxImage.src = item.full_image_path;
  lightboxImage.alt = `${item.label} from ${item.doc_id}`;
  lightboxTitle.textContent = item.doc_id;

  const pageLabel = item.page_number ? `page ${item.page_number}` : "page ?";
  const regionLabel = item.region_index ? `region ${item.region_index}` : "region ?";
  lightboxCaption.textContent = `${item.year}-${item.month} • ${item.label} • ${pageLabel} • ${regionLabel}`;
  lightboxLink.href = item.full_image_path;
  lightboxLink.textContent = "Open original image";

  if (typeof lightbox.showModal === "function") {
    lightbox.showModal();
    return;
  }

  lightbox.setAttribute("open", "");
}

function closeLightbox() {
  if (typeof lightbox.close === "function") {
    lightbox.close();
    return;
  }
  lightbox.removeAttribute("open");
}

lightboxClose.addEventListener("click", closeLightbox);
lightbox.addEventListener("click", (event) => {
  if (event.target === lightbox) {
    closeLightbox();
  }
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && lightbox.hasAttribute("open")) {
    closeLightbox();
  }
});

async function init() {
  setLoadingState("Gallery", "Loading decade summaries...");

  try {
    state.indexData = await fetchJson(indexPath);
    totalImageCount.textContent = formatCount(state.indexData.total_images);
    generationNote.textContent = formatGeneratedAt(state.indexData.generated_at);
    renderDecadeList();

    const firstDecade = state.indexData.decades[0]?.decade;
    if (firstDecade) {
      loadDecade(firstDecade);
      return;
    }

    setLoadingState("Gallery", "No images were indexed yet.");
  } catch (error) {
    totalImageCount.textContent = "Unavailable";
    generationNote.textContent = "";
    setLoadingState("Gallery", `Failed to load gallery index: ${error.message}`);
  }
}

init();

