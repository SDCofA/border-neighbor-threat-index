/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   BNTI v2.0 — Core Engine
   Data loading, state, poller
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */

const BNTI = {
  data: window.BNTI_DATA || null,
  trendChart: null,
  lastFocusedElement: null,

  // ── Helpers ──
  getIndexValue(obj) {
    if (!obj) return 0;
    const value = obj.main_index ?? obj.index;
    const num = Number(value);
    return Number.isFinite(num) ? num : 0;
  },

  parsePoints(list) {
    if (!Array.isArray(list)) return [];
    return list
      .map(item => {
        const value = this.getIndexValue(item);
        const ts = item.timestamp ? new Date(item.timestamp) : null;
        if (!ts || Number.isNaN(ts.getTime())) return null;
        return { ts, value, type: item.type || 'historical', confidence: item.confidence };
      })
      .filter(Boolean)
      .sort((a, b) => a.ts - b.ts);
  },

  formatTime(date) {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  },

  formatDateTime(date) {
    return date.toLocaleString([], { year: 'numeric', month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit' });
  },

  formatUtcWindow(startIso, endIso) {
    const start = startIso ? new Date(startIso) : null;
    const end = endIso ? new Date(endIso) : null;
    if (!start || Number.isNaN(start.getTime()) || !end || Number.isNaN(end.getTime())) return '6H WINDOW';
    const format = value => `${String(value.getUTCHours()).padStart(2, '0')}:${String(value.getUTCMinutes()).padStart(2, '0')}`;
    return `${format(start)}-${format(end)} UTC`;
  },

  escapeHtml(value) {
    return String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  },

  setStatusClasses(element, status) {
    element.classList.remove('critical', 'elevated', 'stable');
    if (status === 'CRITICAL') element.classList.add('critical');
    else if (status === 'ELEVATED') element.classList.add('elevated');
    else element.classList.add('stable');
  },

  // ── Header Update ──
  updateHeader() {
    const status = (this.data?.meta?.status || 'STABLE').toUpperCase();
    const statusClass = status.includes('CRITICAL') ? 'CRITICAL' : status.includes('ELEVATED') ? 'ELEVATED' : 'STABLE';
    const statusPill = document.getElementById('status-pill');
    statusPill.textContent = status;
    this.setStatusClasses(statusPill, statusClass);

    // Add live dot
    if (!statusPill.querySelector('.live-dot')) {
      statusPill.insertAdjacentHTML('afterbegin', '<span class="live-dot"></span>');
    }

    const lastUpdate = this.data?.meta?.generated_at ? new Date(this.data.meta.generated_at) : null;
    document.getElementById('last-update').textContent = lastUpdate && !Number.isNaN(lastUpdate.getTime()) ? this.formatDateTime(lastUpdate) : '--';
    const freshness = BNTIFreshness.evaluate(
      this.data?.meta?.generated_at,
      new Date(),
      Number(this.data?.meta?.refresh_target_minutes) || 120
    );
    document.getElementById('next-update').textContent = freshness.label;
    statusPill.classList.remove('data-current', 'data-delayed', 'data-stale', 'data-unknown');
    statusPill.classList.add(`data-${freshness.level}`);
  },

  // ── Metrics Update ──
  updateMetrics(historyPoints) {
    const status = (this.data?.meta?.status || 'STABLE').toUpperCase();
    const statusClass = status.includes('CRITICAL') ? 'CRITICAL' : status.includes('ELEVATED') ? 'ELEVATED' : 'STABLE';

    const idx = this.getIndexValue(this.data?.meta);
    const metricEl = document.getElementById('main-index');
    metricEl.textContent = idx.toFixed(2);
    metricEl.className = `metric-value ${statusClass.toLowerCase()}`;

    document.getElementById('status-text').textContent = status;

    let trendText = 'Trend: --';
    if (historyPoints.length >= 2) {
      const latest = historyPoints[historyPoints.length - 1];
      const prev = historyPoints[historyPoints.length - 2];
      const delta = latest.value - prev.value;
      const arrow = delta > 0 ? '▲' : delta < 0 ? '▼' : '━';
      trendText = `${arrow} ${delta >= 0 ? '+' : ''}${delta.toFixed(2)}`;
    }
    document.getElementById('trend-text').textContent = trendText;

    const totalSignals = Object.values(this.data?.countries || {}).reduce((sum, c) => {
      return sum + (Array.isArray(c.events) ? c.events.length : 0);
    }, 0);
    document.getElementById('signal-text').textContent = `SIGNALS: ${totalSignals}`;
  },

  // ── Weights Update ──
  updateWeights() {
    const weightsEl = document.getElementById('weights-table');
    weightsEl.innerHTML = '';
    const weights = this.data?.methodology?.weights || {};

    Object.entries(weights)
      .sort(([, a], [, b]) => b - a)
      .forEach(([label, value]) => {
        const row = document.createElement('div');
        row.className = 'weight-row';
        const pretty = label.replace(/_/g, ' ').toUpperCase();
        const val = Number(value);
        const valClass = val >= 0 ? 'positive' : 'negative';
        row.innerHTML = `<div>${pretty}</div><div class="weight-value ${valClass}">${val > 0 ? '+' : ''}${val.toFixed(1)}</div>`;
        weightsEl.appendChild(row);
      });
  },

  updateRegionalBriefing() {
    const container = document.getElementById('regional-summary');
    if (!container) return;

    const summary = this.data?.briefing?.regional_summary_6h;
    if (!summary || !Array.isArray(summary.bullets) || !summary.bullets.length) {
      container.innerHTML = '<div class="briefing-empty">NO CURRENT BRIEFING</div>';
      return;
    }

    const bulletsHtml = summary.bullets
      .map(item => `<li>${this.escapeHtml(item)}</li>`)
      .join('');

    const watchHtml = summary.watch
      ? `<div class="briefing-watch"><span>WATCH</span>${this.escapeHtml(summary.watch)}</div>`
      : '';

    container.innerHTML = `
      <div class="briefing-meta">
        <span>${this.escapeHtml(this.formatUtcWindow(summary.slot_start, summary.slot_end))}</span>
        <span>${Number(summary.source_event_count) || 0} SIGNALS</span>
      </div>
      <div class="briefing-headline">${this.escapeHtml(summary.headline)}</div>
      <ul class="briefing-list">${bulletsHtml}</ul>
      ${watchHtml}
    `;
  },

  updateScenarioDisclosure() {
    const issued = document.getElementById('scenario-issued');
    const horizon = document.getElementById('scenario-horizon');
    const uncertainty = document.getElementById('scenario-uncertainty');
    if (!issued || !horizon || !uncertainty) return;

    const issueTime = this.data?.meta?.generated_at ? new Date(this.data.meta.generated_at) : null;
    const points = this.parsePoints(this.data?.forecast);
    issued.textContent = issueTime && !Number.isNaN(issueTime.getTime())
      ? this.formatDateTime(issueTime)
      : 'Not recorded';

    if (issueTime && !Number.isNaN(issueTime.getTime()) && points.length) {
      const hours = Math.max(0, Math.round((points[points.length - 1].ts - issueTime) / 3600000));
      horizon.textContent = `${hours || 6} hours`;
    } else {
      horizon.textContent = '6 hours';
    }

    const confidences = points
      .map(point => Number(point.confidence))
      .filter(Number.isFinite);
    uncertainty.textContent = confidences.length
      ? `Heuristic confidence ${Math.round(Math.min(...confidences) * 100)}–${Math.round(Math.max(...confidences) * 100)}%; no calibrated interval`
      : 'Heuristic confidence unavailable; no calibrated interval';
  },

  updateEarlyWarning() {
    const warning = this.data?.early_warning;
    const componentsEl = document.getElementById('early-warning-components');
    if (!warning || !componentsEl) return;

    const score = Number(warning.score);
    document.getElementById('early-warning-score').textContent = Number.isFinite(score) ? score.toFixed(1) : '--';
    document.getElementById('early-warning-level').textContent = warning.level || '--';
    document.getElementById('early-warning-confidence').textContent = warning.confidence
      ? `${warning.confidence} · ${Number(warning.confidence_score || 0).toFixed(0)}% coverage`
      : '--';
    document.getElementById('early-warning-horizon').textContent = warning.horizon || '0–7 days';
    const issued = warning.issued_at ? new Date(warning.issued_at) : null;
    document.getElementById('early-warning-issued').textContent = issued && !Number.isNaN(issued.getTime())
      ? this.formatDateTime(issued)
      : '--';

    const componentDetail = component => {
      if (component.id === 'narrative_pressure') {
        return `${Number(component.precursor_event_count) || 0} precursor events · ${Number(component.independent_sources) || 0} domains`;
      }
      if (component.id === 'cross_market_dislocation') {
        const indicators = (component.indicators || []).filter(item => item.available);
        return indicators.length
          ? indicators.map(item => `${item.label}: z ${Number(item.anomaly_z).toFixed(1)}`).join(' · ')
          : 'Market series unavailable';
      }
      return `${Number(component.rising_entities) || 0}/${Number(component.entities_compared) || 0} entities rising`;
    };

    componentsEl.innerHTML = (warning.components || []).map(component => `
      <article class="early-warning-component ${component.available ? '' : 'unavailable'}">
        <div><span>${this.escapeHtml(component.label)}</span><strong>${Number(component.score || 0).toFixed(1)}</strong></div>
        <div class="early-warning-bar"><i style="width:${Math.max(0, Math.min(100, Number(component.score) || 0))}%"></i></div>
        <p>${this.escapeHtml(component.available ? componentDetail(component) : 'Component unavailable; excluded from aggregate')}</p>
      </article>
    `).join('');

    const alerts = warning.alerts || [];
    document.getElementById('early-warning-alerts').innerHTML = alerts.length
      ? alerts.map(alert => `<div><strong>${this.escapeHtml(alert.level)} · ${this.escapeHtml(alert.title)}</strong><span>${this.escapeHtml(alert.why)}</span></div>`).join('')
      : '<div><strong>ROUTINE</strong><span>No component is above the alert threshold.</span></div>';

    const health = warning.data_health || {};
    document.getElementById('early-warning-health').innerHTML = `
      <span>${Number(health.events_considered) || 0} events</span>
      <span>${Number(health.independent_sources) || 0} domains</span>
      <span>${Number(health.market_series_available) || 0}/3 market series</span>
      <span>${Number(health.available_components) || 0}/3 components</span>
    `;
  },

  // ── Render All ──
  renderAll() {
    if (!this.data) return;
    const historyPoints = this.parsePoints(this.data.history);
    const forecastPoints = this.parsePoints(this.data.forecast);
    this.updateHeader();
    this.updateMetrics(historyPoints);
    this.updateWeights();
    this.updateRegionalBriefing();
    this.updateScenarioDisclosure();
    this.updateEarlyWarning();
    BNTIMap.update(this.data);
    BNTIStream.update(this.data);
    BNTICharts.init(historyPoints, forecastPoints);
  },

  // ── Data Poller ──
  startDataPoller() {
    setInterval(async () => {
      try {
        const res = await fetch(`bnti_data.json?t=${Date.now()}`);
        if (!res.ok) return;
        const newData = await res.json();
        if (newData?.meta?.generated_at && newData.meta.generated_at !== this.data?.meta?.generated_at) {
          this.data = newData;
          this.renderAll();
        }
      } catch (e) {
        console.log('Poll:', e.message);
      }
    }, 60000);

    setInterval(() => this.updateHeader(), 60000);
  },

  // ── UTC Clock ──
  startClock() {
    const el = document.getElementById('utc-clock');
    if (!el) return;
    const tick = () => {
      const now = new Date();
      el.textContent = now.toUTCString().slice(17, 25) + ' UTC';
    };
    tick();
    setInterval(tick, 1000);
  },

  // ── Init ──
  init() {
    this.renderAll();
    this.startDataPoller();
    this.startClock();
    this.initModal();
  },

  // ── Modal ──
  initModal() {
    const link = document.getElementById('methodology-link');
    const modal = document.getElementById('methodology-modal');
    const close = document.getElementById('close-modal');
    if (!link || !modal) return;

    const content = modal.querySelector('.modal-content');
    const closeModal = () => {
      modal.style.display = 'none';
      document.body.style.overflow = '';
      link.setAttribute('aria-expanded', 'false');
      this.lastFocusedElement?.focus();
    };

    link.addEventListener('click', e => {
      e.preventDefault();
      this.lastFocusedElement = document.activeElement;
      modal.style.display = 'block';
      document.body.style.overflow = 'hidden';
      link.setAttribute('aria-expanded', 'true');
      content?.focus();
    });
    close?.addEventListener('click', closeModal);
    modal.addEventListener('click', e => {
      if (e.target === modal) {
        closeModal();
      }
    });
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape' && modal.style.display === 'block') closeModal();
    });
  }
};
