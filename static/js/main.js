/* ═══════════════════════════════════════════════════════════
   Scale Gest V2 — main.js
══════════════════════════════════════════════════════════════ */

/* ──────────────────────────────────────────────────────────
   THÈME
─────────────────────────────────────────────────────────── */
function getTheme() {
  return document.documentElement.getAttribute('data-theme') || 'dark';
}
function setTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('cm-theme', theme);
  _syncChartColors();
}

var themeBtn = document.getElementById('theme-toggle');
if (themeBtn) {
  themeBtn.addEventListener('click', function () {
    var next = getTheme() === 'dark' ? 'light' : 'dark';
    setTheme(next);
    this.style.transform = 'scale(0.88) rotate(15deg)';
    var btn = this;
    setTimeout(function () { btn.style.transform = ''; }, 180);
  });
}

/* ──────────────────────────────────────────────────────────
   DEVISE
─────────────────────────────────────────────────────────── */
var CURRENCY_KEY = 'sg-currency';

// Taux de conversion approximatifs par rapport à EUR
var RATES = {
  EUR: { symbol: '€',    before: false, rate: 1      },
  USD: { symbol: '$',    before: true,  rate: 1.08   },
  GBP: { symbol: '£',    before: true,  rate: 0.86   },
  CAD: { symbol: 'CA$',  before: true,  rate: 1.47   },
  XOF: { symbol: 'FCFA', before: false, rate: 655.96 },
  MAD: { symbol: 'DH',   before: false, rate: 10.85  },
};

function getCurrentCurrency() {
  return localStorage.getItem(CURRENCY_KEY) || 'EUR';
}

function formatMoney(amountEUR, currencyCode) {
  var c = RATES[currencyCode] || RATES['EUR'];
  var converted = amountEUR * c.rate;
  // Arrondi adapté : FCFA sans décimale, autres avec 2 décimales
  var decimals = (currencyCode === 'XOF') ? 0 : 2;
  var formatted = converted.toLocaleString('fr-FR', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals
  });
  return c.before ? c.symbol + ' ' + formatted : formatted + ' ' + c.symbol;
}

function applyDevise(code) {
  document.querySelectorAll('.money[data-amount]').forEach(function (el) {
    var raw = parseFloat(el.getAttribute('data-amount')) || 0;
    el.textContent = formatMoney(raw, code);
  });
  // Met à jour aussi le total en temps réel de la saisie CA
  updateSalesTotal();
}

function initDevise() {
  var sel = document.getElementById('currency-select');
  if (!sel) return;
  var saved = getCurrentCurrency();
  sel.value = saved;
  applyDevise(saved);
  sel.addEventListener('change', function () {
    localStorage.setItem(CURRENCY_KEY, this.value);
    applyDevise(this.value);
  });
}
initDevise();

/* ──────────────────────────────────────────────────────────
   SIDEBAR
   Mobile (≤768px) : toujours fermée au chargement.
   Desktop : restaurée depuis localStorage.
─────────────────────────────────────────────────────────── */
var sidebar       = document.getElementById('sidebar');
var sidebarToggle = document.getElementById('sidebar-toggle');
var overlay       = document.getElementById('sidebar-overlay');

function isMobile() { return window.innerWidth <= 768; }

function getSidebarState() {
  return document.documentElement.getAttribute('data-sidebar') || 'open';
}

function _setSidebarAttr(state) {
  document.documentElement.setAttribute('data-sidebar', state);
}

function openSidebar() {
  _setSidebarAttr('open');
  if (!isMobile()) localStorage.setItem('cm-sidebar', 'open');
}

function closeSidebar() {
  _setSidebarAttr('closed');
  if (!isMobile()) localStorage.setItem('cm-sidebar', 'closed');
}

function toggleSidebar() {
  getSidebarState() === 'open' ? closeSidebar() : openSidebar();
}

if (sidebarToggle) sidebarToggle.addEventListener('click', toggleSidebar);
if (overlay)       overlay.addEventListener('click', closeSidebar);

document.addEventListener('keydown', function (e) {
  if (e.key === 'Escape' && getSidebarState() === 'open') closeSidebar();
});

// Clic sur un lien nav → fermer sur mobile
document.querySelectorAll('.nav-item').forEach(function (link) {
  link.addEventListener('click', function () {
    if (isMobile()) _setSidebarAttr('closed');
  });
});

// Init : sur mobile on force toujours fermé (sans toucher localStorage)
(function initSidebar() {
  if (!sidebar) return;
  if (isMobile()) {
    _setSidebarAttr('closed');
  }
  // Desktop : le script <head> a déjà appliqué l'état depuis localStorage
}());

// Resize : ajustement si on passe de desktop à mobile
window.addEventListener('resize', function () {
  if (!sidebar) return;
  if (isMobile() && getSidebarState() === 'open') {
    _setSidebarAttr('closed');
  }
});

/* ──────────────────────────────────────────────────────────
   DATE LIVE
─────────────────────────────────────────────────────────── */
function updateLiveDate() {
  var el = document.getElementById('live-date');
  if (!el) return;
  el.textContent = new Date().toLocaleDateString('fr-FR', {
    weekday: 'long', day: '2-digit', month: 'long', year: 'numeric',
    hour: '2-digit', minute: '2-digit'
  });
}
updateLiveDate();
setInterval(updateLiveDate, 30000);

/* ──────────────────────────────────────────────────────────
   FLASH AUTO-DISMISS
─────────────────────────────────────────────────────────── */
document.querySelectorAll('.flash').forEach(function (el) {
  setTimeout(function () {
    el.style.transition = 'opacity 0.35s, transform 0.35s';
    el.style.opacity    = '0';
    el.style.transform  = 'translateY(-6px)';
    setTimeout(function () { el.remove(); }, 380);
  }, 4000);
});

/* ──────────────────────────────────────────────────────────
   TOTAL SAISIE CA
─────────────────────────────────────────────────────────── */
function updateSalesTotal() {
  var total = 0;
  document.querySelectorAll('.ca-input').forEach(function (inp) {
    total += parseFloat(inp.value.replace(',', '.')) || 0;
  });
  var el = document.getElementById('sales-total');
  if (el) {
    var code = getCurrentCurrency();
    el.textContent = formatMoney(total, code);
  }
}
document.querySelectorAll('.ca-input').forEach(function (inp) {
  inp.addEventListener('input', updateSalesTotal);
});
updateSalesTotal();

/* ──────────────────────────────────────────────────────────
   CONFIRM data-confirm
─────────────────────────────────────────────────────────── */
document.querySelectorAll('[data-confirm]').forEach(function (el) {
  el.addEventListener('click', function (e) {
    if (!confirm(this.dataset.confirm)) e.preventDefault();
  });
});

/* ──────────────────────────────────────────────────────────
   CHART.JS — couleurs selon thème
─────────────────────────────────────────────────────────── */
var COLORS = {
  dark: {
    grid: 'rgba(255,255,255,0.06)', text: '#646A90',
    tooltip: '#1E2333', ttTitle: '#F0F2FF', ttBody: '#B8BDDB',
    ttBorder: 'rgba(255,255,255,0.08)',
    line1: '#F97316', line1bg: 'rgba(249,115,22,0.12)',
    line2: '#F59E0B', line2bg: 'rgba(245,158,11,0.08)',
    donut: ['#F97316','#F59E0B','#14B8A6','#EF4444','#3B82F6',
            '#8B5CF6','#EC4899','#22C55E','#FB923C','#84CC16']
  },
  light: {
    grid: 'rgba(0,0,0,0.07)', text: '#7A7450',
    tooltip: '#FFFFFF', ttTitle: '#18150A', ttBody: '#3D3822',
    ttBorder: 'rgba(0,0,0,0.10)',
    line1: '#F97316', line1bg: 'rgba(249,115,22,0.10)',
    line2: '#D97706', line2bg: 'rgba(217,119,6,0.08)',
    donut: ['#F97316','#D97706','#0D9488','#DC2626','#2563EB',
            '#7C3AED','#DB2777','#16A34A','#EA580C','#65A30D']
  }
};

function _chartC() { return COLORS[getTheme()] || COLORS.dark; }
window.chartColors   = _chartC;
window._chartInst    = window._chartInst || [];
window.registerChart = function (chart, type) { window._chartInst.push({ chart: chart, type: type }); };

function _syncChartColors() {
  if (typeof Chart === 'undefined') return;
  var c = _chartC();
  window._chartInst.forEach(function (item) {
    if (!item.chart) return;
    if (item.chart.options.scales) {
      Object.values(item.chart.options.scales).forEach(function (axis) {
        if (axis.grid)  axis.grid.color  = c.grid;
        if (axis.ticks) axis.ticks.color = c.text;
      });
    }
    var plugins = item.chart.options.plugins;
    if (plugins && plugins.legend && plugins.legend.labels)
      plugins.legend.labels.color = c.text;
    if (plugins && plugins.tooltip) {
      plugins.tooltip.backgroundColor = c.tooltip;
      plugins.tooltip.titleColor      = c.ttTitle;
      plugins.tooltip.bodyColor       = c.ttBody;
      plugins.tooltip.borderColor     = c.ttBorder;
    }
    if (item.type === 'line') {
      var ds = item.chart.data.datasets;
      if (ds[0]) { ds[0].borderColor = c.line1; ds[0].backgroundColor = c.line1bg; }
      if (ds[1]) { ds[1].borderColor = c.line2; ds[1].backgroundColor = c.line2bg; }
    }
    item.chart.update('none');
  });
}

(function applyChartDefaults() {
  if (typeof Chart === 'undefined') return;
  var c = _chartC();
  Chart.defaults.color                            = c.text;
  Chart.defaults.font.family                      = "'Inter','Segoe UI',sans-serif";
  Chart.defaults.font.size                        = 12;
  Chart.defaults.plugins.tooltip.backgroundColor = c.tooltip;
  Chart.defaults.plugins.tooltip.titleColor      = c.ttTitle;
  Chart.defaults.plugins.tooltip.bodyColor       = c.ttBody;
  Chart.defaults.plugins.tooltip.borderColor     = c.ttBorder;
  Chart.defaults.plugins.tooltip.borderWidth     = 1;
  Chart.defaults.plugins.tooltip.padding         = 10;
  Chart.defaults.plugins.tooltip.cornerRadius    = 8;
}());
