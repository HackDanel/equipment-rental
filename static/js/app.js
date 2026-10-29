// Мобильное меню
document.querySelectorAll('[data-nav-toggle]').forEach((btn) => {
  const nav = document.querySelector('[data-nav]');
  btn.addEventListener('click', () => {
    const open = nav.classList.toggle('is-open');
    btn.setAttribute('aria-expanded', String(open));
  });
});

// Подтверждение опасных действий: <form data-confirm="Текст вопроса">
document.querySelectorAll('form[data-confirm]').forEach((form) => {
  form.addEventListener('submit', (e) => {
    if (!window.confirm(form.dataset.confirm)) e.preventDefault();
  });
});

// Живой расчёт стоимости брони: при смене дат и количества спрашиваем /api/quote/.
// Сервер всё равно пересчитывает цену и доступность при сохранении — это только подсказка.
document.querySelectorAll('form[data-quote]').forEach((form) => {
  const box = form.querySelector('[data-quote-box]');
  const field = (name) => form.querySelector(`[name=${name}]`);
  const out = (key) => box.querySelector(`[data-q=${key}]`);
  const start = field('start_date');
  const end = field('end_date');
  const qty = field('quantity');
  const money = (v) => `${Number(v).toLocaleString('ru-RU', { minimumFractionDigits: 2 })} ₽`;
  const days = (n) => `${n} ${n % 10 === 1 && n % 100 !== 11 ? 'сутки' : 'суток'}`;
  let timer;
  let seq = 0;

  const update = async () => {
    if (!start.value || !end.value) return;
    // Дата окончания не может быть раньше начала — подсказываем это прямо в поле.
    end.min = start.value;
    const params = new URLSearchParams({ equipment: form.dataset.equipment, start: start.value, end: end.value, qty: qty.value || '1' });
    const my = ++seq;
    let data;
    try {
      const resp = await fetch(`${form.dataset.quote}?${params}`, { headers: { Accept: 'application/json' } });
      data = await resp.json();
    } catch {
      return;
    }
    if (my !== seq) return; // пришёл ответ на устаревший запрос
    const err = out('error');
    if (data.days) {
      out('days').textContent = days(data.days);
      out('discount').textContent = data.discount_percent ? `−${data.discount_percent}%` : 'нет';
      out('available').textContent = `${data.available} шт.`;
      out('deposit').textContent = money(data.deposit);
      out('total').textContent = money(data.total);
    } else {
      ['days', 'discount', 'available', 'deposit', 'total'].forEach((k) => { out(k).textContent = '—'; });
    }
    const messages = Object.values(data.errors || {});
    box.classList.toggle('is-error', messages.length > 0);
    err.hidden = messages.length === 0;
    err.textContent = messages.join(' ');
  };

  [start, end, qty].forEach((el) => el.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(update, 250);
  }));
  update();
});
