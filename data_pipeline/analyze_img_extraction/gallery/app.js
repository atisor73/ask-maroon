const indexPath = "./data/index.json";
const numberFormatter = new Intl.NumberFormat();

const state = {
  indexData: null,
  activeDecade: null,
  activeDecadePayload: null,
  decadeCache: new Map(),
  lightboxItems: [],
  lightboxIndex: -1,
  lightboxRotation: 0,
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
const lightboxRotateLeft = document.querySelector("#lightbox-rotate-left");
const lightboxRotateRight = document.querySelector("#lightbox-rotate-right");
const lightboxClose = document.querySelector("#lightbox-close");
const lightboxPrev = document.querySelector("#lightbox-prev");
const lightboxNext = document.querySelector("#lightbox-next");
const lightboxShell = document.querySelector("#lightbox .lightbox-shell");

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

  return `Generated ${date.toLocaleDateString()}`;
}

function setLoadingState(title, subtitle) {
  detailTitle.textContent = title;
  detailSubtitle.textContent = subtitle;
  yearSections.innerHTML = "";
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
  button.setAttribute(
    "aria-label",
    `${item.label} from ${item.doc_id}${item.page_number ? `, page ${item.page_number}` : ""}`
  );

  const image = document.createElement("img");
  image.className = "image-card-thumb";
  image.src = item.thumbnail_path;
  image.alt = `${item.label} from ${item.doc_id}`;
  image.loading = "lazy";
  image.addEventListener("error", () => {
    image.src = item.full_image_path;
  });

  button.appendChild(image);
  button.addEventListener("click", () => openLightbox(item));
  return button;
}

function labelSortRank(label) {
  const normalized = (label || "").toLowerCase();
  const ranks = {
    photograph: 0,
    map: 1,
    "editorial cartoon": 2,
    illustration: 3,
    "comics cartoon": 4,
  };
  return normalized in ranks ? ranks[normalized] : 99;
}

function groupItemsByLabel(items) {
  const groups = new Map();
  items.forEach((item) => {
    const label = item.label || "unknown";
    if (!groups.has(label)) {
      groups.set(label, []);
    }
    groups.get(label).push(item);
  });

  return Array.from(groups.entries()).sort((left, right) => {
    const leftLabel = left[0];
    const rightLabel = right[0];
    const rankDifference = labelSortRank(leftLabel) - labelSortRank(rightLabel);
    if (rankDifference !== 0) {
      return rankDifference;
    }
    return leftLabel.localeCompare(rightLabel);
  });
}

function flattenDecadeItems(decadePayload) {
  const flattened = [];
  (decadePayload?.years || []).forEach((yearPayload) => {
    groupItemsByLabel(yearPayload.items || []).forEach(([, groupItems]) => {
      flattened.push(...groupItems);
    });
  });
  return flattened;
}

function renderYearItems(container, items) {
  container.innerHTML = "";
  const groups = groupItemsByLabel(items);

  groups.forEach(([label, groupItems]) => {
    const groupSection = document.createElement("section");
    groupSection.className = "label-group";

    const heading = document.createElement("div");
    heading.className = "label-group-heading";

    const title = document.createElement("h4");
    title.textContent = label;
    heading.appendChild(title);

    const count = document.createElement("p");
    count.textContent = `${formatCount(groupItems.length)} images`;
    heading.appendChild(count);

    const grid = document.createElement("div");
    grid.className = "image-grid";
    groupItems.forEach((item) => {
      grid.appendChild(buildImageButton(item));
    });

    groupSection.appendChild(heading);
    groupSection.appendChild(grid);
    container.appendChild(groupSection);
  });
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

  const body = document.createElement("div");
  body.className = "year-body";
  body.hidden = true;

  function collapseSiblingYears() {
    const siblingSections = Array.from(yearSections.querySelectorAll(".year-section"));
    siblingSections.forEach((siblingSection) => {
      if (siblingSection === section) {
        return;
      }

      const siblingButton = siblingSection.querySelector(".year-toggle");
      const siblingBody = siblingSection.querySelector(".year-body");
      if (!siblingButton || !siblingBody) {
        return;
      }

      siblingButton.setAttribute("aria-expanded", "false");
      siblingBody.hidden = true;
      siblingSection.classList.remove("is-open");
    });
  }

  button.addEventListener("click", () => {
    const expanded = button.getAttribute("aria-expanded") === "true";
    if (!expanded) {
      collapseSiblingYears();
    }
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
  state.activeDecadePayload = decadePayload;
  state.lightboxItems = flattenDecadeItems(decadePayload);
  state.lightboxIndex = -1;
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

function isLightboxOpen() {
  return Boolean(lightbox?.open || lightbox?.hasAttribute("open"));
}

function updateLightboxNav() {
  const hasMultipleItems = state.lightboxItems.length > 1;
  lightboxPrev.hidden = !hasMultipleItems;
  lightboxNext.hidden = !hasMultipleItems;

  if (!hasMultipleItems) {
    return;
  }

  lightboxPrev.disabled = state.lightboxIndex <= 0;
  lightboxNext.disabled = state.lightboxIndex >= state.lightboxItems.length - 1;
}

function applyLightboxRotation() {
  lightboxImage.style.transform = `rotate(${state.lightboxRotation}deg)`;
}

function showLightboxItem(index) {
  if (index < 0 || index >= state.lightboxItems.length) {
    return;
  }

  const item = state.lightboxItems[index];
  state.lightboxIndex = index;
  state.lightboxRotation = 0;
  lightboxImage.src = item.full_image_path;
  lightboxImage.alt = `${item.label} from ${item.doc_id}`;
  lightboxTitle.textContent = item.doc_id;

  const pageLabel = item.page_number ? `page ${item.page_number}` : "page ?";
  const regionLabel = item.region_index ? `region ${item.region_index}` : "region ?";
  lightboxCaption.textContent = `${item.year}-${item.month} • ${item.label} • ${pageLabel} • ${regionLabel}`;
  applyLightboxRotation();
  updateLightboxNav();
}

function openLightbox(item) {
  const matchingIndex = state.lightboxItems.findIndex(
    (candidate) => candidate.source_relative_path === item.source_relative_path
  );
  const nextIndex = matchingIndex >= 0 ? matchingIndex : 0;
  showLightboxItem(nextIndex);

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

function stepLightbox(direction) {
  if (!isLightboxOpen()) {
    return;
  }

  const nextIndex = state.lightboxIndex + direction;
  if (nextIndex < 0 || nextIndex >= state.lightboxItems.length) {
    return;
  }

  showLightboxItem(nextIndex);
}

function rotateLightbox(deltaDegrees) {
  if (!isLightboxOpen()) {
    return;
  }

  state.lightboxRotation = (state.lightboxRotation + deltaDegrees) % 360;
  applyLightboxRotation();
}

lightboxRotateLeft.addEventListener("click", () => {
  rotateLightbox(-90);
});
lightboxRotateRight.addEventListener("click", () => {
  rotateLightbox(90);
});
lightboxClose.addEventListener("click", closeLightbox);
lightboxPrev.addEventListener("click", () => {
  stepLightbox(-1);
});
lightboxNext.addEventListener("click", () => {
  stepLightbox(1);
});
lightbox.addEventListener("click", (event) => {
  if (event.target === lightbox) {
    closeLightbox();
  }
});
lightboxShell.addEventListener("click", (event) => {
  if (event.target === lightboxShell) {
    closeLightbox();
  }
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && isLightboxOpen()) {
    closeLightbox();
    return;
  }

  if (event.key === "ArrowLeft" && isLightboxOpen()) {
    stepLightbox(-1);
    return;
  }

  if (event.key === "ArrowRight" && isLightboxOpen()) {
    stepLightbox(1);
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
