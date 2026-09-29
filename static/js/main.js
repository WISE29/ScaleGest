/* ═══════════════════════════════════════════════════════════
   Chatter Manager V2 — main.js
   Architecture : data-theme et data-sidebar sur <html>.
   Gestion sécurisée : le bouton theme-toggle peut être absent
   (page login n'a pas de sidebar).
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
   SIDEBAR
─────────────────────────────────────────────────────────── */
var sidebar       = document.getElementById('sidebar');
var sidebarToggle = document.getElementById('sidebar-toggle');
var overlay       = document.getElementById('sidebar-overlay');

function getSidebarState() {
  return document.documentElement.getAttribute('data-sidebar') || 'open';
}

function setSidebarState(state) {
  document.documentElement.setAttribute('data-sidebar', state);
  localStorage.setItem('cm-sidebar', state);
}

function openSidebar()  { setSidebarState('open'); }
function closeSidebar() { setSidebarState('closed'); }

function toggleSidebar() {
  getSidebarState() === 'open' ? closeSidebar() : openSidebar();
}

if (sidebarToggle) sidebarToggle.addEventListener('click', toggleSidebar);
if (overlay)       overlay.addEventListener('click', closeSidebar);

document.addEventListener('keydown', function (e) {
  if (e.key === 'Escape' && getSidebarState() === 'open') closeSidebar();
});

(function initSidebar() {
  if (!sidebar) return;          // page login : pas de sidebar
  var isMobile = window.innerWidth <= 768;
  var saved    = localStorage.getItem('cm-sidebar');
  if (isMobile && !saved) closeSidebar();
}());

window.addEventListener('resize', function () {
  if (!sidebar) return;
  if (window.innerWidth <= 768 && getSidebarState() === 'open') {
    document.documentElement.setAttribute('data-sidebar', 'closed');
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
  if (el) el.textContent = total.toLocaleString('fr-FR', {
    minimumFractionDigits: 2, maximumFractionDigits: 2
  }) + ' €';
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
    grid: 'rgba(255,255,255,0.06)', text: '#7878A0',
    tooltip: '#1A1A2F', ttTitle: '#F0F0FA', ttBody: '#C4C4D8',
    ttBorder: 'rgba(255,255,255,0.08)',
    line1: '#6C63FF', line1bg: 'rgba(108,99,255,0.12)',
    line2: '#F59E0B', line2bg: 'rgba(245,158,11,0.08)',
    donut: ['#6C63FF','#F59E0B','#10B981','#EF4444','#3B82F6',
            '#8B5CF6','#EC4899','#14B8A6','#F97316','#84CC16']
  },
  light: {
    grid: 'rgba(0,0,0,0.07)', text: '#7272A0',
    tooltip: '#FFFFFF', ttTitle: '#12122A', ttBody: '#3A3A5C',
    ttBorder: 'rgba(0,0,0,0.10)',
    line1: '#6C63FF', line1bg: 'rgba(108,99,255,0.10)',
    line2: '#D97706', line2bg: 'rgba(217,119,6,0.08)',
    donut: ['#6C63FF','#D97706','#059669','#DC2626','#2563EB',
            '#7C3AED','#DB2777','#0D9488','#EA580C','#65A30D']
  }
};

function _chartC() { return COLORS[getTheme()] || COLORS.dark; }

window.chartColors   = _chartC;
window._chartInst    = window._chartInst || [];
window.registerChart = function (chart, type) {
  window._chartInst.push({ chart: chart, type: type });
};

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

(function () {
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
