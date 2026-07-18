/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━
   BNTI v2.0 — Charts Module
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━ */

const BNTICharts = {
    init(historyPoints, forecastPoints) {
        const ctx = document.getElementById('trendChart');
        const emptyEl = document.getElementById('chart-empty');

        if (BNTI.trendChart) BNTI.trendChart.destroy();

        if (!historyPoints.length) {
            emptyEl.style.display = 'flex';
            return;
        }

        emptyEl.style.display = 'none';
        const labels = [...historyPoints, ...forecastPoints].map(p => BNTI.formatTime(p.ts));
        const historyValues = historyPoints.map(p => p.value);
        const forecastValues = [
            ...Array(Math.max(historyPoints.length - 1, 0)).fill(null),
            historyPoints[historyPoints.length - 1]?.value ?? null,
            ...forecastPoints.map(p => p.value)
        ];

        BNTI.trendChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels,
                datasets: [
                    {
                        label: 'Observed index',
                        data: historyValues,
                        borderColor: '#c9a24b',
                        borderWidth: 1.5,
                        pointRadius: 0,
                        tension: 0.3,
                        fill: {
                            target: 'origin',
                            above: 'rgba(201, 162, 75, 0.08)'
                        }
                    },
                    {
                        label: 'Scenario projection',
                        data: forecastValues,
                        borderColor: '#7d7565',
                        borderDash: [3, 4],
                        borderWidth: 1,
                        pointRadius: 0,
                        tension: 0.3
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: '#1a1a1a',
                        borderColor: '#c9a24b',
                        borderWidth: 1,
                        titleFont: { family: 'JetBrains Mono', size: 9 },
                        bodyFont: { family: 'JetBrains Mono', size: 10 },
                        callbacks: {
                            label: ctx => `INDEX: ${ctx.parsed.y.toFixed(2)}`
                        }
                    }
                },
                scales: {
                    x: { display: false },
                    y: {
                        min: 1,
                        max: 10,
                        ticks: {
                            color: '#7d7565',
                            font: { family: 'JetBrains Mono', size: 8 }
                        },
                            grid: { color: 'rgba(236, 230, 216, 0.05)' }
                    }
                }
            }
        });
    }
};
