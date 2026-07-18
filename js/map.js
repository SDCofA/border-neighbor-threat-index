/* ━━━━━━━━━━━━━━━━━━━━━━━━━
   BNTI v2.0 — Map Module
   ━━━━━━━━━━━━━━━━━━━━━━━━━ */

const BNTIMap = {
    selectedCountry: null,

    renderDetail(name, data) {
        const detail = document.getElementById('country-detail');
        const country = data?.countries?.[name];
        if (!detail || !country) return;
        const score = BNTI.getIndexValue(country);
        const status = score >= 7 ? 'Critical' : score >= 4 ? 'Elevated' : 'Stable';
        const events = Array.isArray(country.events) ? country.events.length : 0;
        this.selectedCountry = name;
        detail.innerHTML = `
            <strong>${BNTI.escapeHtml(name)}</strong><br>
            <em>${status} · ${score.toFixed(2)} / 10 · ${events} current signals</em><br>
            Analytical signal from the latest published snapshot; review source events and methodology before use.
        `;
    },

    bindInteractions(data) {
        const shapes = document.querySelectorAll('#map-svg .country-shape');
        shapes.forEach(el => {
            const name = el.getAttribute('data-country');
            if (!data?.countries?.[name]) return;
            el.setAttribute('tabindex', '0');
            el.setAttribute('role', 'button');
            el.setAttribute('aria-label', `Inspect ${name} analytical signal`);
            if (el.dataset.bound === 'true') return;
            const activate = () => this.renderDetail(name, BNTI.data);
            el.addEventListener('click', activate);
            el.addEventListener('keydown', event => {
                if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    activate();
                }
            });
            el.dataset.bound = 'true';
        });

        const search = document.getElementById('country-search');
        if (search && search.dataset.bound !== 'true') {
            search.addEventListener('input', event => {
                const query = event.target.value.trim().toLowerCase();
                if (!query) return;
                const match = Object.keys(BNTI.data?.countries || {})
                    .find(name => name.toLowerCase().startsWith(query));
                if (match) this.renderDetail(match, BNTI.data);
            });
            search.dataset.bound = 'true';
        }
    },

    update(data) {
        const overlay = document.getElementById('map-overlay-stats');
        const countries = Object.entries(data?.countries || {})
            .map(([name, c]) => ({ name, score: BNTI.getIndexValue(c) }))
            .sort((a, b) => b.score - a.score);

        let overlayHtml = '<h4>Regional Threats</h4>';
        countries.forEach(c => {
            let color = 'var(--stable)';
            if (c.score >= 7) color = 'var(--critical)';
            else if (c.score >= 4) color = 'var(--elevated)';
            overlayHtml += `<div class="map-row"><span>${c.name.toUpperCase()}</span><span style="color:${color}">${c.score.toFixed(2)}</span></div>`;
        });
        overlay.innerHTML = overlayHtml;

        document.querySelectorAll('#map-svg .country-shape').forEach(el => {
            const name = el.getAttribute('data-country');
            const country = data?.countries?.[name];
            const score = country ? BNTI.getIndexValue(country) : 0;
            const status = score >= 7 ? 'critical' : score >= 4 ? 'elevated' : 'stable';
            el.classList.remove('critical', 'elevated', 'stable');
            el.classList.add(status);
            let title = el.querySelector('title');
            if (!title) {
                title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
                el.appendChild(title);
            }
            title.textContent = `${name}: ${score.toFixed(2)} (${status.toUpperCase()})`;
        });
        this.bindInteractions(data);
        if (this.selectedCountry && data?.countries?.[this.selectedCountry]) {
            this.renderDetail(this.selectedCountry, data);
        }
    }
};
