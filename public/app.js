/**
 * Lógica de interfaz para "Noticias debajo de la tierra"
 * - 5 noticias de España + 5 Internacionales (con foto, enfoque progresista sin clickbait y radar Rojo=Izq / Azul=Der)
 * - Sección "Habla con un hetero" (resumen exprés de fútbol: resultados y goleadores)
 */

const state = {
  data: null,
  filter: "all", // 'all' | 'blindspot'
};

document.addEventListener("DOMContentLoaded", () => {
  initTheme();
  initFilterButtons();
  loadDailyData();
});

/* --- Gestión de Modo Claro / Oscuro --- */
function initTheme() {
  const savedTheme = localStorage.getItem("ndlt-theme");
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const initialTheme = savedTheme || (prefersDark ? "dark" : "light");
  applyTheme(initialTheme);

  const toggleBtn = document.getElementById("theme-toggle");
  toggleBtn.addEventListener("click", () => {
    const current = document.documentElement.getAttribute("data-theme");
    const next = current === "dark" ? "light" : "dark";
    applyTheme(next);
    localStorage.setItem("ndlt-theme", next);
  });
}

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  const label = document.getElementById("theme-label");
  const icon = document.getElementById("theme-icon");
  if (theme === "dark") {
    label.textContent = "Modo claro";
    icon.textContent = "☀";
  } else {
    label.textContent = "Modo oscuro";
    icon.textContent = "☾";
  }
}

/* --- Filtros --- */
function initFilterButtons() {
  const buttons = document.querySelectorAll(".filter-chip");
  buttons.forEach((btn) => {
    btn.addEventListener("click", () => {
      buttons.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      state.filter = btn.getAttribute("data-filter");
      renderAllSections();
    });
  });
}

/* --- Carga de ./data.json --- */
async function loadDailyData() {
  const spainContainer = document.getElementById("spain-topics-container");
  try {
    const response = await fetch("./data.json", { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const data = await response.json();
    state.data = data;
    renderHeaderAndBriefing(data);
    renderAllSections();
  } catch (error) {
    console.error("Error cargando data.json:", error);
    spainContainer.innerHTML = `
      <div class="empty-state">
        No se pudo cargar <code>data.json</code>. Ejecuta primero <code>python generator.py</code>.
      </div>
    `;
  }
}

function renderAllSections() {
  if (!state.data) return;

  const spainTopics = state.data.spain_topics || state.data.top_topics || [];
  const intlTopics = state.data.international_topics || [];
  const sportsData = state.data.habla_con_un_hetero || null;

  renderTopicList("spain-topics-container", spainTopics, "España");
  renderTopicList("intl-topics-container", intlTopics, "Internacional");
  renderSportsSection(sportsData);
}

function renderHeaderAndBriefing(data) {
  const dateEl = document.getElementById("edition-date");
  if (data.date_formatted) {
    dateEl.textContent = data.date_formatted;
  }

  if (data.edition_title) {
    document.getElementById("edition-subtitle").textContent = data.edition_title;
  }

  if (data.daily_briefing) {
    const briefingSection = document.getElementById("briefing-section");
    const briefingText = document.getElementById("daily-briefing-text");
    const generatedTime = document.getElementById("generated-time");

    briefingText.textContent = data.daily_briefing;
    if (data.generated_at) {
      const dt = new Date(data.generated_at);
      if (!isNaN(dt)) {
        generatedTime.textContent = `Actualizado ${dt.toLocaleTimeString("es-ES", {
          hour: "2-digit",
          minute: "2-digit",
        })}`;
      }
    }
    briefingSection.hidden = false;
  }
}

/* --- Renderizado de listas de temas (España e Internacional) --- */
function renderTopicList(containerId, topicsArray, label) {
  const container = document.getElementById(containerId);
  if (!container) return;

  const filtered = topicsArray.filter((t) => {
    if (state.filter === "blindspot") {
      return t.blindspot && t.blindspot.has_blindspot;
    }
    return true;
  });

  if (filtered.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        No hay noticias de ${escapeHTML(label)} con Punto Ciego en esta edición.
      </div>
    `;
    return;
  }

  container.innerHTML = filtered.map((topic, idx) => createTopicCardHTML(topic, idx)).join("");
}

function createTopicCardHTML(topic, idx) {
  const cov = topic.coverage || { left: 0, center: 0, right: 0 };
  const bs = topic.blindspot || { has_blindspot: false, ignored_by: "ninguno", explanation: "" };
  const title = topic.editorial_title || topic.neutral_title || "";
  const imageUrl = (topic.image_url || "").trim();
  const hasImage = imageUrl.startsWith("http://") || imageUrl.startsWith("https://");

  const blindspotBadge = bs.has_blindspot
    ? `<span class="blindspot-pill" title="${escapeHTML(bs.explanation)}">
         👁️ Punto Ciego · Ignorado por la ${escapeHTML(bs.ignored_by)}
       </span>`
    : "";

  const blindspotBanner =
    bs.has_blindspot && bs.explanation
      ? `<div class="blindspot-banner">
           <strong>Alerta de Punto Ciego:</strong> ${escapeHTML(bs.explanation)}
         </div>`
      : "";

  const figureHTML = hasImage
    ? `<figure class="topic-figure">
         <img
           class="topic-image"
           src="${escapeAttribute(imageUrl)}"
           alt="${escapeAttribute(title)}"
           loading="lazy"
           referrerpolicy="no-referrer"
           onerror="this.closest('.topic-figure').style.display='none'; this.closest('.topic-Editorial-grid').classList.remove('has-image');"
         />
         ${
           topic.image_caption
             ? `<figcaption class="topic-figcaption">${escapeHTML(topic.image_caption)}</figcaption>`
             : ""
         }
       </figure>`
    : "";

  const perspectivesHTML = (topic.perspectives || [])
    .map(
      (p) => `
      <a class="perspective-card" href="${escapeAttribute(p.url)}" target="_blank" rel="noopener noreferrer">
        <div>
          <div class="perspective-top">
            <span class="source-name">${escapeHTML(p.source_name)}</span>
            <span class="bias-tag bias-${escapeAttribute(p.bias)}">${escapeHTML(p.bias)}</span>
          </div>
          <h4 class="perspective-headline">“${escapeHTML(p.headline)}”</h4>
          <p class="perspective-angle">${escapeHTML(p.angle)}</p>
        </div>
        <span class="perspective-link">Leer en ${escapeHTML(p.source_name)} ↗</span>
      </a>
    `
    )
    .join("");

  return `
    <article class="topic-card">
      <div class="topic-top-meta">
        <div class="topic-number-cat">
          <span class="topic-index">#0${escapeHTML(String(topic.id || idx + 1))}</span>
          <span class="topic-category">${escapeHTML(topic.category || "Actualidad")}</span>
        </div>
        ${blindspotBadge}
      </div>

      <div class="topic-Editorial-grid ${hasImage ? "has-image" : ""}">
        <div class="topic-text-col">
          <h3 class="topic-title">${escapeHTML(title)}</h3>
          <p class="topic-summary">${escapeHTML(topic.executive_summary)}</p>
        </div>
        ${figureHTML}
      </div>

      ${blindspotBanner}

      <div class="coverage-box" aria-label="Distribución de cobertura ideológica">
        <div class="coverage-header">
          <span>BALANCE DE COBERTURA</span>
          <span>${(topic.perspectives || []).length} ${
            (topic.perspectives || []).length === 1 ? "medio" : "medios"
          }</span>
        </div>
        <div class="coverage-bar">
          <div class="bar-segment bar-left" style="width: ${Number(cov.left) || 0}%"></div>
          <div class="bar-segment bar-center" style="width: ${Number(cov.center) || 0}%"></div>
          <div class="bar-segment bar-right" style="width: ${Number(cov.right) || 0}%"></div>
        </div>
        <div class="coverage-labels">
          <span class="cov-label-left">🔴 Izquierda ${Number(cov.left) || 0}%</span>
          <span class="cov-label-center">⚪ Centro ${Number(cov.center) || 0}%</span>
          <span class="cov-label-right">🔵 Derecha ${Number(cov.right) || 0}%</span>
        </div>
      </div>

      <div class="perspectives-heading">Cómo titula y enfoca cada periódico</div>
      <div class="perspectives-grid">
        ${perspectivesHTML}
      </div>
    </article>
  `;
}

/* --- Renderizado de "Habla con un hetero" (Deportes / Fútbol) --- */
function renderSportsSection(sports) {
  const container = document.getElementById("sports-container");
  const introEl = document.getElementById("hetero-intro");
  if (!container) return;

  if (!sports || !Array.isArray(sports.matches_and_news) || sports.matches_and_news.length === 0) {
    container.innerHTML = `<div class="empty-state">Hoy no hay crónicas futboleras disponibles.</div>`;
    return;
  }

  if (sports.intro_joke && introEl) {
    introEl.textContent = sports.intro_joke;
  }

  container.innerHTML = sports.matches_and_news
    .map(
      (item) => `
      <a class="sports-card" href="${escapeAttribute(item.url)}" target="_blank" rel="noopener noreferrer">
        <div>
          <span class="sports-comp">⚽ ${escapeHTML(item.competition)}</span>
          <h3 class="sports-headline">${escapeHTML(item.headline)}</h3>
          <p class="sports-talking-point">${escapeHTML(item.talking_point)}</p>
        </div>
        <span class="perspective-link">Ver crónica por si te preguntan más ↗</span>
      </a>
    `
    )
    .join("");
}

function escapeHTML(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function escapeAttribute(str) {
  if (!str) return "#";
  return escapeHTML(str);
}
