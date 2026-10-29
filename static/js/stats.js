(() => {
  const data = JSON.parse(document.getElementById('stats-data').textContent);
  if (!window.Chart) return;

  const css = getComputedStyle(document.documentElement);
  const color = (name) => css.getPropertyValue(name).trim();
  // Цвета берутся из токенов CSS, поэтому графики сами подстраиваются под тёмную тему.
  const s1 = color('--series-1');
  const s2 = color('--series-2');
  const surface = color('--surface');

  Chart.defaults.color = color('--muted');
  Chart.defaults.borderColor = color('--line');
  Chart.defaults.font.family = css.fontFamily;
  Chart.defaults.font.size = 12;
  Chart.defaults.maintainAspectRatio = false;
  Chart.defaults.plugins.tooltip.backgroundColor = color('--ink');
  Chart.defaults.plugins.tooltip.titleColor = surface;
  Chart.defaults.plugins.tooltip.bodyColor = surface;
  // Уважаем системную настройку «уменьшить движение».
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) Chart.defaults.animation = false;

  const money = (v) => `${Math.round(Number(v)).toLocaleString('ru-RU')} ₽`;
  // На осях — сокращённо («120 тыс. ₽»), в подсказках — точная сумма.
  const short = (v) => `${Number(v).toLocaleString('ru-RU', { notation: 'compact', maximumFractionDigits: 1 })} ₽`;
  const bar = { borderRadius: 4, borderSkipped: 'start', borderWidth: 0, maxBarThickness: 28 };
  const single = { plugins: { legend: { display: false } } };
  const grid = { grid: { color: color('--line'), drawTicks: false }, border: { display: false } };
  const noGrid = { grid: { display: false }, border: { display: false } };

  new Chart(document.getElementById('ch-revenue'), {
    type: 'bar',
    data: {
      labels: data.months,
      datasets: [
        { ...bar, label: 'Аренда', data: data.revenue, backgroundColor: s1 },
        { ...bar, label: 'Штрафы', data: data.fines, backgroundColor: s2 },
      ],
    },
    options: {
      interaction: { mode: 'index', intersect: false },
      scales: { x: { ...noGrid, ticks: { maxRotation: 0, autoSkipPadding: 8 } }, y: { ...grid, beginAtZero: true, ticks: { callback: short } } },
      plugins: { legend: { position: 'top', align: 'start', labels: { boxWidth: 10, boxHeight: 10 } },
        tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${money(c.parsed.y)}` } } },
    },
  });

  new Chart(document.getElementById('ch-bookings'), {
    type: 'line',
    data: { labels: data.months, datasets: [{ label: 'Броней', data: data.bookings, borderColor: s1, backgroundColor: s1, borderWidth: 2, pointRadius: 4, pointHoverRadius: 6, pointBorderColor: surface, pointBorderWidth: 2, tension: 0 }] },
    options: { ...single, interaction: { mode: 'index', intersect: false },
      scales: { x: { ...noGrid, ticks: { maxRotation: 0, autoSkipPadding: 8 } }, y: { ...grid, beginAtZero: true, ticks: { precision: 0 } } } },
  });

  const hbar = (id, labels, values, fmt, colors, axis = fmt) => new Chart(document.getElementById(id), {
    type: 'bar',
    data: { labels, datasets: [{ ...bar, data: values, backgroundColor: colors || s1 }] },
    options: { ...single, indexAxis: 'y',
      scales: { x: { ...grid, beginAtZero: true, ticks: { callback: axis, maxRotation: 0, maxTicksLimit: 6 } }, y: noGrid },
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => fmt(c.parsed.x) } } } },
  });

  hbar('ch-top', data.top.labels, data.top.values, money, null, short);
  hbar('ch-util', data.utilization.labels, data.utilization.values, (v) => `${v}%`);
  // Просрочка — статус «внимание», поэтому только она окрашена отдельно.
  const red = color('--red');
  hbar('ch-statuses', data.statuses.labels, data.statuses.values, (v) => `${v}`,
    data.statuses.labels.map((l) => (l === 'Просрочено' ? red : s1)));
  hbar('ch-fines', data.fine_kinds.labels, data.fine_kinds.values, money, null, short);
})();
