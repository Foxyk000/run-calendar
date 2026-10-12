# Календарь забегов России

`scraper.py` раз в сутки собирает забеги из источников (+ `manual.json`), чистит прошедшие, склеивает дубли
и пишет `events.json`. `index.html` читает этот файл. Всё крутится в GitHub Actions и публикуется на GitHub Pages.

## Запуск
1. Создайте репозиторий, залейте эти файлы в ветку `main`.
2. Settings → Pages → Source: **GitHub Actions**.
3. Actions → *update-and-deploy* → Run workflow (дальше сам, ежедневно в 06:00 МСК).

Локально: `pip install -r requirements.txt && python scraper.py && python -m http.server`

## Как добавить источник
Добавьте запись в `SOURCES` в `scraper.py`. Если сайт отдаёт schema.org/Event (JSON-LD), хватит `kind: "jsonld"`.
Для остальных напишите функцию-парсер по образцу `parse_begaem`. Ручные правки (исправить дату, добавить старт) — в `manual.json`:
он имеет приоритет над парсерами.
