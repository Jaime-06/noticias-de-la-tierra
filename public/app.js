/**
 * Lógica de interfaz para "Noticias debajo de la tierra"
 * Lee data.json y renderiza los 5 grandes temas de España, barras de sesgo,
 * indicadores de Punto Ciego (Blindspot) y lecturas de The New Yorker.
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
      renderTopics();
    });
  });
}

/* --- Carga de public/data.json --- */
async function loadDailyData() {
  const container = document.getElementById("topics-container");
  try {
    const response = await fetch("./data.json", { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const data = await response.json();
    state.data = data;
    renderHeaderAndBriefing(data);
    renderTopics();
    renderInternational(data.international_reads || []);
  } catch (error) {
    console.error("Error cargando data.json:", error);
    container.innerHTML = `
      <div class="empty-state">
        No se pudo cargar <code>data.json</code>. Ejecuta primero <code>python generator.py</code> o sirve la carpeta <code>public/</code> con un servidor local.
      </div>
    `;
  }
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

/* --- Renderizado de los 5 temas del día --- */
function renderTopics() {
  const container = document.getElementById("topics-container");
  if (!state.data || !Array.isArray(state.data.top_topics)) {
    return;
  }

  const topics = state.data.top_topics.filter((t) => {
    if (state.filter === "blindspot") {
      return t.blindspot && t.blindspot.has_blindspot;
    }
    return true;
  });

  if (topics.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        No hay temas con Punto Ciego (Blindspot) en la edición de hoy.
      </div>
    `;
    return;
  }

  container.innerHTML = topics.map((topic, idx) => createTopicCardHTML(topic, idx)).join("");
}

function createTopicCardHTML(topic, idx) {
  const cov = topic.coverage || { left: 0, center: 0, right: 0 };
  const bs = topic.blindspot || { has_blindspot: false, ignored_by: "ninguno", explanation: "" };

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

      <h2 class="topic-title">${escapeHTML(topic.neutral_title)}</h2>
      <p class="topic-summary">${escapeHTML(topic.executive_summary)}</p>

      ${blindspotBanner}

      <div class="coverage-box" aria-label="Distribución de cobertura ideológica">
        <div class="coverage-header">
          <span>RADAR DE COBERTURA MEDIÁTICA</span>
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
          <span class="cov-label-left">Izquierda ${Number(cov.left) || 0}%</span>
          <span class="cov-label-center">Centro ${Number(cov.center) || 0}%</span>
          <span class="cov-label-right">Derecha ${Number(cov.right) || 0}%</span>
        </div>
      </div>

      <div class="perspectives-heading">Cómo lo enfoca cada medio</div>
      <div class="perspectives-grid">
        ${perspectivesHTML}
      </div>
    </article>
  `;
}

/* --- Renderizado de The New Yorker --- */
function renderInternational(reads) {
  const container = document.getElementById("international-container");
  if (!reads || reads.length === 0) {
    container.innerHTML = `<div class="empty-state">Sin lecturas internacionales disponibles hoy.</div>`;
    return;
  }

  container.innerHTML = reads
    .map(
      (item) => `
      <a class="intl-card" href="${escapeAttribute(item.url)}" target="_blank" rel="noopener noreferrer">
        <div>
          <span class="intl-reason">${escapeHTML(item.reading_Reason || "The New Yorker")}</span>
          <h3 class="intl-title-es">${escapeHTML(item.translated_title)}</h3>
          <div class="intl-title-en">${escapeHTML(item.original_title)}</div>
          <p class="intl-summary">${escapeHTML(item.summary)}</p>
        </div>
        <span class="perspective-link">Leer artículo original en The New Yorker ↗</span>
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
