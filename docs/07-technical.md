# 7. Техническое описание программы

## 7.1. Общие сведения

| Параметр | Значение |
|---|---|
| Наименование | Веб-приложение «Прокат оборудования» (Снаряга) |
| Назначение | Бронирование спортивного, туристического и строительного оборудования, контроль сроков аренды, учёт склада и штрафов, аналитика |
| Язык | Python 3.13 (проверено также на 3.14) |
| Фреймворк | Django 6.0 |
| СУБД | PostgreSQL 17 (рабочая), SQLite 3 (разработка) |
| Сервер приложений | Gunicorn 26, статика — WhiteNoise 6 |
| Клиентская часть | HTML5, CSS3 без фреймворков, JavaScript ES2020, Chart.js 4.4 |
| Объём исходного кода | ≈ 2 500 строк Python (без тестов и миграций), ≈ 930 строк тестов, ≈ 1 260 строк шаблонов, CSS и JS |
| Зависимости | `requirements.txt`: Django, psycopg 3, Pillow, Gunicorn, WhiteNoise |

## 7.2. Модули

| Модуль (`apps/…`) | Ответственность | Основные файлы |
|---|---|---|
| `accounts` | Пользователь с ролью, регистрация, вход, профиль, проверка ролей, счётчик новых броней в меню | `models.py` (User), `forms.py`, `permissions.py`, `context_processors.py` |
| `catalog` | Категории, оборудование, скидки, правила проката; каталог, карточка, API расчёта | `models.py`, `forms.py`, `views.py` |
| `inventory` | Экземпляры и журнал склада; ремонт, списание, поступление | `models.py` (Unit, UnitEvent), `services.py`, `views.py` |
| `bookings` | Брони, выданные экземпляры, штрафы, история; кабинет клиента и рабочее место менеджера | `models.py`, `services.py`, `forms.py`, `views.py`, `management/commands/seed_demo.py` |
| `dashboard` | Панель администратора, статистика | `views.py`, `stats.py` |

Зависимости: `bookings` использует `accounts`, `catalog` и `inventory`; `catalog` вызывает сервисы `bookings`
для календаря и фильтра «свободно на даты»; `dashboard` читает данные всех модулей.

## 7.3. Модели данных

| Модель | Таблица | Ключевые поля |
|---|---|---|
| `User` | `accounts_user` | `role`, `phone`, свойства `is_client`, `is_manager`, `is_admin_role` |
| `Category` | `catalog_category` | `name`, `group` |
| `Equipment` | `catalog_equipment` | `price_per_day`, `deposit`, `replacement_cost`, `photo`, `is_active` |
| `DiscountTier` | `catalog_discounttier` | `min_days`, `percent` |
| `RentalSettings` | `catalog_rentalsettings` | одна запись: `late_fee_multiplier`, `max_rental_days`, `max_advance_days`; `load()` |
| `Unit` | `inventory_unit` | `inventory_number`, `condition`, `status`; `Unit.WORKING` — бронируемые статусы |
| `UnitEvent` | `inventory_unitevent` | `kind`, `condition`, `booking`, `author` |
| `Booking` | `bookings_booking` | даты, `quantity`, `status`, цены на момент брони; свойства `days`, `is_overdue`, `overdue_days`, `display_status` |
| `BookingItem` | `bookings_bookingitem` | `unit`, `condition_out`, `condition_in`, `lost` |
| `Fine` | `bookings_fine` | `kind`, `amount`, `is_paid` |
| `StatusChange` | `bookings_statuschange` | `status`, `author`, `comment` |

Подробно — [раздел 4](04-database.md).

## 7.4. Бизнес-логика

`apps/bookings/services.py`:

| Функция | Что делает |
|---|---|
| `overlapping(equipment, start, end, exclude=None)` | активные брони, пересекающие период (включительно); просроченная выдача занимает экземпляры до сегодня |
| `available_count(...)` | исправные экземпляры минус сумма количеств пересекающихся броней |
| `validate_period(start, end)` | дата не в прошлом, не дальше горизонта, конец не раньше начала, срок не больше максимума |
| `quote(equipment, start, end, qty)` | сутки, лучшая скидка, итог (`Decimal`, округление до копеек), залог, доступность |
| `create_booking(...)` | проверки + блокировка оборудования + повторный расчёт доступности + запись истории |
| `confirm`, `reject`, `cancel` | переходы статусов по `TRANSITIONS`, повторная проверка доступности при подтверждении |
| `issue(booking, user, units)` | проверка дат и экземпляров, блокировка строк, `BookingItem` + статус «Выдан» + журнал |
| `late_fee(booking, returned_on)` | сутки просрочки × цена суток × количество × множитель |
| `return_booking(booking, user, lines)` | штраф за просрочку, состояние каждого экземпляра, ремонт/списание, штрафы за повреждение и утерю |
| `availability_calendar(equipment, days)` | свободные экземпляры по дням для карточки |

`apps/inventory/services.py`: `add_units`, `send_to_repair`, `return_from_repair`, `write_off`,
`set_condition` — каждая операция блокирует строку экземпляра и пишет `UnitEvent`.

Все функции, меняющие данные, работают в `transaction.atomic()` и при нарушении правил бросают
`ValidationError` с понятным сообщением — представление показывает его пользователю.

## 7.5. Разграничение доступа

Декораторы в `apps/accounts/permissions.py`: `role_required(*roles)` проверяет вход и роль, иначе 403;
готовые `client_required`, `staff_required` (менеджер и администратор), `admin_required`. Дополнительно:

- клиент видит только свои брони (`services.can_view`), отменить может только свою;
- изменяющие действия принимают только POST (`require_POST`) и защищены CSRF-токеном;
- параметр `next` после регистрации и поступления экземпляров проверяется `url_has_allowed_host_and_scheme`;
- форма сотрудников не открывает клиентов, администратор не может понизить или заблокировать себя.

## 7.6. Статистика (`dashboard/stats.py`)

| Показатель | Как считается |
|---|---|
| Выручка по месяцам | сумма `price_total` броней «Выдано» и «Возвращено» по месяцу даты начала |
| Штрафы по месяцам | сумма `Fine.amount` по месяцу начисления |
| Брони по месяцам | все брони по месяцу даты начала |
| Топ оборудования | 8 позиций с наибольшей выручкой |
| Загрузка парка | экземпляро-сутки в аренде за 30 дней / (экземпляры × 30) по направлениям |
| Брони по статусам | с выделением просроченных из выданных |
| Доля возвратов с просрочкой | возвращённые брони со штрафом за просрочку / все возвращённые |

Графики рисует `static/js/stats.js` (Chart.js). Цвета берутся из CSS-переменных, поэтому графики
подстраиваются под тёмную тему; палитра двух серий проверена на различимость при нарушениях цветового зрения.

## 7.7. Настройки и переменные окружения

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `SECRET_KEY` | небезопасный dev-ключ | ключ подписи сессий и CSRF; на сервере генерируется случайно |
| `DEBUG` | `true` | режим отладки; на сервере `false` |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | разрешённые домены |
| `CSRF_TRUSTED_ORIGINS` | — | origin для проверки CSRF за HTTPS-прокси |
| `SECURE_COOKIES` | `true` при `DEBUG=false` | cookie сессии и CSRF только по HTTPS |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | — | PostgreSQL; без `DB_NAME` — SQLite |
| `MEDIA_ROOT` | `./media` | каталог фото оборудования |
| `TIME_ZONE` | `Asia/Novosibirsk` | часовой пояс; от него зависит «сегодня» в проверках дат |

Константы: `MAX_PHOTO_SIZE = 5 МБ`, минимальная длина пароля 8 символов. Правила проката (множитель
штрафа, сроки) хранятся в БД и меняются администратором.

## 7.8. Команды управления

| Команда | Назначение |
|---|---|
| `python manage.py migrate` | создать или обновить схему БД |
| `python manage.py seed_demo [--password P] [--bookings N] [--seed S]` | заполнить пустую базу демо-данными |
| `python manage.py createsuperuser` | создать администратора |
| `python manage.py test` | автотесты |
| `python e2e/scenarios.py` | сквозные сценарии в браузере (нужен Playwright) |
| `python manage.py collectstatic` | собрать статику (выполняется при сборке Docker-образа) |

## 7.9. Как расширять

- **Новый статус брони.** Значение в `Status`, переходы в `TRANSITIONS` (`bookings/models.py`), стиль
  `.badge--<значение>` в `static/css/app.css`, миграция.
- **Уведомления.** Отправка письма в сервисных функциях после записи `StatusChange`; ежедневная рассылка
  о приближении срока возврата — команда управления по cron.
- **Онлайн-оплата.** Поле статуса оплаты у брони и штрафа, обработчик уведомлений платёжного сервиса.
- **Несколько пунктов проката.** Модель `Location`, ссылка на неё у `Unit`; `available_count` фильтрует
  экземпляры по пункту выдачи.
