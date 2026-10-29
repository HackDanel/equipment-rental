"""Сквозные сценарии в браузере (раздел 5.5 документации).

Нужен Playwright с Chromium: pip install playwright && playwright install chromium.
Запускать на свежей демо-базе (seed_demo) при работающем сервере:
    python manage.py runserver 127.0.0.1:8200
    python e2e/scenarios.py
Сценарии меняют данные (создают брони, принимают возврат), поэтому повторный прогон — после пересоздания базы.
"""
import datetime as dt
import re
from pathlib import Path

from playwright.sync_api import sync_playwright
B = 'http://127.0.0.1:8200'
ROOT = Path(__file__).resolve().parent.parent
today = dt.date.today()
res = []
def ok(n, cond, note=''):
    res.append((n, bool(cond), note)); print(('OK  ' if cond else 'FAIL'), n, note)

def page(b, w=1280):
    ctx = b.new_context(viewport={'width': w, 'height': 900})
    ctx.route('**/fonts.g*/**', lambda r: r.abort())
    pg = ctx.new_page(); pg.set_default_timeout(15000)
    pg.on('dialog', lambda d: d.accept())
    return pg

def go(pg, url): pg.goto(B + url, wait_until='domcontentloaded')

def login(pg, user, nxt=''):
    go(pg, '/accounts/login/' + (f'?next={nxt}' if nxt else ''))
    pg.fill('input[name=username]', user); pg.fill('input[name=password]', 'demo12345')
    with pg.expect_navigation(wait_until='domcontentloaded'): pg.click('main form button.btn')

with sync_playwright() as p:
    b = p.chromium.launch()
    # 1 каталог
    pg = page(b)
    go(pg, f'/?group=tourism&q=палатка&date_from={today+dt.timedelta(10)}&date_to={today+dt.timedelta(12)}&sort=price')
    names = pg.locator('.tile__name').all_inner_texts()
    ok(1, names and all('алатка' in n for n in names), str(names))
    # 2 бронирование гостем через вход
    go(pg, '/equipment/9/')  # палатка 3-местная
    pg.click('text=Войти, чтобы забронировать'); pg.wait_for_url('**/login/**')
    pg.fill('input[name=username]', 'client'); pg.fill('input[name=password]', 'demo12345')
    with pg.expect_navigation(wait_until='domcontentloaded'): pg.click('main form button.btn')
    ok('2a', '/equipment/9/' in pg.url, pg.url)
    s, e = today + dt.timedelta(20), today + dt.timedelta(22)
    pg.fill('#id_start_date', s.isoformat()); pg.fill('#id_end_date', e.isoformat()); pg.fill('#id_quantity', '2')
    pg.wait_for_timeout(1200)
    disc = pg.inner_text('[data-q=discount]'); total = pg.inner_text('[data-q=total]')
    ok('2b', disc == '−10%', f'скидка {disc}, итог {total}')
    with pg.expect_navigation(wait_until='domcontentloaded'): pg.click('#book button.btn')
    ok('2c', 'Ожидает подтверждения' in pg.inner_text('main'), pg.url)
    bid = int(re.search(r'/bookings/(\d+)/', pg.url).group(1))
    # 3 нехватка
    go(pg, '/equipment/9/')
    pg.fill('#id_start_date', s.isoformat()); pg.fill('#id_end_date', e.isoformat()); pg.fill('#id_quantity', '50')
    pg.wait_for_timeout(1000)
    live = pg.inner_text('[data-q=error]')
    with pg.expect_navigation(wait_until='domcontentloaded'): pg.click('#book button.btn')
    err = pg.locator('.errorlist').all_inner_texts()
    ok(3, 'свободно' in ' '.join(err) and 'свободно' in live, f'{live} | {err}')
    # 4-5 менеджер подтверждает; выдаёт другую бронь (подтверждённую на сегодня нельзя — создаём на сегодня)
    pm = page(b); login(pm, 'manager1')
    go(pm, '/manager/?tab=new'); ok('4a', pm.locator(f'a:text-is("{bid}")').count() == 1)
    go(pm, f'/bookings/{bid}/')
    with pm.expect_navigation(wait_until='domcontentloaded'): pm.click('text=Подтвердить')
    ok('4b', 'Забронировано' in pm.inner_text('.ticket'))
    # бронь на сегодня для выдачи
    go(pg, '/equipment/13/')  # горелка
    pg.fill('#id_start_date', today.isoformat()); pg.fill('#id_end_date', (today + dt.timedelta(1)).isoformat()); pg.fill('#id_quantity', '1')
    with pg.expect_navigation(wait_until='domcontentloaded'): pg.click('#book button.btn')
    bid2 = int(re.search(r'/bookings/(\d+)/', pg.url).group(1))
    go(pm, f'/bookings/{bid2}/')
    with pm.expect_navigation(wait_until='domcontentloaded'): pm.click('text=Подтвердить')
    pm.locator('input[name=units]').first.check()
    unit_label = pm.locator('input[name=units]').first.evaluate('e => e.parentElement.innerText')
    with pm.expect_navigation(wait_until='domcontentloaded'): pm.click('button:text("Выдать")')
    ok('5a', 'Выдано' in pm.inner_text('.ticket'), unit_label)
    inv = unit_label.split(' ')[0]
    go(pm, f'/stock/units/?q={inv}')
    ok('5b', 'Выдан' in pm.inner_text('tbody'), inv)
    # 6 просрочка
    go(pm, '/manager/?tab=overdue'); first = pm.locator('tbody a.mono').first.inner_text()
    go(pm, f'/bookings/{first}/')
    ok(6, 'Просрочено' in pm.inner_text('.ticket') and 'штраф при возврате сегодня' in pm.inner_text('.ticket'), f'бронь {first}')
    # 7 приём с повреждением
    pm.select_option('select[name$=_condition]', 'damaged'); pm.fill('input[name$=_damage_fee]', '3000'); pm.fill('input[name$=_note]', 'скол корпуса')
    with pm.expect_navigation(wait_until='domcontentloaded'): pm.click('button:text("Принять возврат")')
    fines = pm.inner_text('main')
    ok('7a', 'Просрочка возврата' in fines and 'Повреждение' in fines and 'Возвращено' in fines)
    unit_link = pm.locator('.table-wrap td.mono a').first.inner_text()
    go(pm, f'/stock/units/?q={unit_link}'); ok('7b', 'В ремонте' in pm.inner_text('tbody'), unit_link)
    # 8 оплата штрафа
    go(pm, f'/bookings/{first}/')
    n_unpaid = pm.locator('text=не оплачен').count()
    with pm.expect_navigation(wait_until='domcontentloaded'): pm.locator('button:text("отметить оплату")').first.click()
    ok(8, pm.locator('text=не оплачен').count() == n_unpaid - 1, f'{n_unpaid} -> {pm.locator("text=не оплачен").count()}')
    # 9 ремонт
    go(pm, f'/stock/units/?q={unit_link}'); pm.click(f'a:text-is("{unit_link}")'); pm.wait_for_load_state('domcontentloaded')
    pm.select_option('form[action$="repaired/"] select', 'good')
    with pm.expect_navigation(wait_until='domcontentloaded'): pm.click('button:text("Вернуть на склад")')
    ok(9, 'На складе' in pm.inner_text('main'))
    # 10 администратор
    pa = page(b); login(pa, 'admin')
    go(pa, '/panel/equipment/new/')
    pa.select_option('#id_category', label='Палатки и тенты'); pa.fill('#id_name', 'Палатка-тест E2E')
    pa.fill('#id_price_per_day', '650'); pa.fill('#id_deposit', '3000'); pa.fill('#id_replacement_cost', '15000')
    pa.set_input_files('#id_photo', str(ROOT / 'seed/photos/tent-3.jpg'))
    with pa.expect_navigation(wait_until='domcontentloaded'): pa.click('main form button.btn')
    eid = int(re.search(r'/panel/equipment/(\d+)/', pa.url).group(1))
    pa.fill('form[action*="/add/"] input[name=count]', '3')
    with pa.expect_navigation(wait_until='domcontentloaded'): pa.click('button:text("Добавить")')
    go(pa, f'/equipment/{eid}/')
    ok(10, '3 шт.' in pa.inner_text('.facts') and pa.locator('.photo img').count() == 1)
    # 11 права
    go(pg, '/manager/'); c403 = 'Нет доступа' in pg.inner_text('main')
    go(pm, '/panel/'); m403 = 'Нет доступа' in pm.inner_text('main')
    ok(11, c403 and m403)
    # 12 мобильная
    pmob = page(b, 375); widths = []
    for u in ['/', '/equipment/9/']:
        go(pmob, u); widths.append(pmob.evaluate('document.documentElement.scrollWidth'))
    login(pmob, 'manager1'); go(pmob, '/manager/'); widths.append(pmob.evaluate('document.documentElement.scrollWidth'))
    ok(12, all(w <= 375 for w in widths), str(widths))
    # отмена клиентом
    go(pg, f'/bookings/{bid2}/'); ok('extra', pg.locator('text=Отменить бронь').count() == 0, 'выданную нельзя отменить')
    b.close()
print('\nИТОГО', sum(r[1] for r in res), 'из', len(res))
