# Прокат оборудования «Снаряга»

Веб-приложение для пункта проката спортивного, туристического и строительного оборудования: клиент
выбирает оборудование, видит свободные даты и стоимость и бронирует его; менеджер подтверждает брони,
выдаёт и принимает конкретные экземпляры, фиксирует состояние и начисляет штрафы; администратор ведёт
каталог, тарифы, склад и сотрудников и смотрит статистику.

Стек: Python 3.13+, Django 6.0, PostgreSQL 17, HTML/CSS/JS, Chart.js, Docker Compose.

Опубликовано: https://rental.37.194.184.235.sslip.io · Репозиторий: https://github.com/HackDanel/equipment-rental (приватный)

## Документация

1. [Анализ предметной области и аналогов](docs/01-analysis.md)
2. [Функциональные и нефункциональные требования](docs/02-requirements.md)
3. [Архитектура, роли, статусы, маршруты, макеты](docs/03-architecture.md)
4. [База данных: ER-диаграмма, таблицы, ограничения](docs/04-database.md)
5. [Тестирование](docs/05-testing.md)
6. [Руководство пользователя](docs/06-user-guide.md)
7. [Техническое описание программы](docs/07-technical.md)
8. [Развёртывание и сопровождение](docs/08-deployment.md)

Отчёт по практике и презентация: [docs/report/](docs/report/). Postman-коллекция: [docs/postman/](docs/postman/).

## Локальный запуск для разработки (SQLite)

```sh
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_demo                    # или createsuperuser
.venv/bin/python manage.py runserver 127.0.0.1:8200
```

Без переменной `DB_NAME` используется SQLite (`db.sqlite3`), с ней — PostgreSQL (см. `.env.example`).

Демо-входы после `seed_demo`: `client`, `manager1`, `admin`; пароль `demo12345`
(свой пароль: `seed_demo --password ...`).

## Запуск в Docker (PostgreSQL)

```sh
cp .env.example .env              # задать SECRET_KEY
docker compose up -d --build      # http://127.0.0.1:8200
docker compose exec web python manage.py seed_demo
```

## Деплой на сервер

```sh
deploy/deploy.sh b450-remote      # синхронизировать код и перезапустить стек
```

Первый запуск создаёт на сервере `~/rental/.env` со случайными `SECRET_KEY` и `DB_PASSWORD`. Приложение
слушает только `127.0.0.1:8210`, наружу его отдаёт Apache — `deploy/apache-rental.conf`. Подробно —
[раздел 8](docs/08-deployment.md).

## Тесты

```sh
.venv/bin/python manage.py test   # 91 тест (на SQLite 1 тест параллельных броней пропускается)
python e2e/scenarios.py           # сценарии в браузере, нужен Playwright и запущенный сервер
```

## Структура

```
config/      настройки и корневые URL
apps/
  accounts/  пользователи и роли
  catalog/   категории, оборудование, тарифы, каталог и API расчёта
  inventory/ экземпляры и журнал склада
  bookings/  брони, выдача и приём, штрафы, кабинет клиента, рабочее место менеджера
  dashboard/ панель администратора и статистика
templates/   HTML-шаблоны
static/      CSS и JS
seed/        фото для демо-данных
e2e/         сквозные сценарии в браузере
deploy/      скрипты и конфигурация сервера
docs/        документация
```

Фото демо-оборудования — Wikimedia Commons, источники и лицензии: [seed/photos/CREDITS.md](seed/photos/CREDITS.md).
