"""Общие настройки сайта: блок между маркерами `# BEGIN ENGINE SETTINGS …` и `# END ENGINE SETTINGS` в zensical.toml
продукта переписывается содержимым zensical.base.toml движка.

Запуск из корня репозитория продукта (в CI после слияния в main — общий workflow движка .github/workflows/build.yml):

    python engine/py/site_settings.py              # обновить блок и записать zensical.toml, если изменился
    python engine/py/site_settings.py --check      # только сверить: код возврата 1, если блок устарел

Зачем
-----
Тема (каталог engine/custom), язык, логотип, возможности, шрифты, цветовые схемы и расширения Markdown одни для всех
продуктов предприятия. Они хранятся в одном месте — zensical.base.toml движка, — а в zensical.toml каждого продукта
попадают этим скриптом. Чтобы изменить настройку для всех продуктов, её меняют в движке и выпускают новую версию: при
следующей сборке каждого продукта блок обновится.

Как устроен zensical.toml продукта
----------------------------------
1. [project] — название сайта, адреса, автор (у продукта свои);
2. блок меню BEGIN/END GENERATED NAV (формирует nav.py);
3. блок BEGIN/END ENGINE SETTINGS — общие настройки (этот скрипт); вручную не правят;
4. таблицы продукта, каждая со своим заголовком (например, [project.extra.tracker] с адресом трекера).

Ключи [project] должны стоять до блока: после заголовка таблицы ([project.theme] в блоке) ключ без своего заголовка
попал бы в эту таблицу. Если маркеров в файле нет, блок добавляется после блока меню (или в конец файла).
Перед записью скрипт проверяет, что zensical.toml остаётся корректным TOML (например, что продукт не задаёт таблицу,
которая уже есть в общих настройках); иначе файл не меняется.

Сторонние пакеты не нужны: только стандартная библиотека Python 3.11+ (модуль tomllib).
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

from common import load, save
from config import NAV_END, SITE_BASE, SITE_BEGIN, SITE_END, SITE_RE, ZENSICAL_CONFIG


def render_block(base: str) -> str:
    return "\n".join([SITE_BEGIN, base.strip("\n"), SITE_END])


def apply(text: str, block: str) -> str:
    """Текст zensical.toml с актуальным блоком общих настроек."""
    if SITE_RE.search(text):
        return SITE_RE.sub(lambda _: block, text, count=1)
    at = text.find(NAV_END)
    if at >= 0:
        at = text.find("\n", at)
        at = len(text) if at < 0 else at + 1
        return text[:at] + "\n" + block + "\n" + text[at:]
    return text.rstrip("\n") + "\n\n" + block + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Общие настройки сайта (тема, расширения) в zensical.toml продукта.")
    parser.add_argument("--config", type=Path, default=ZENSICAL_CONFIG, help="zensical.toml продукта")
    parser.add_argument("--check", action="store_true", help="только сверить, файл не изменяется")
    args = parser.parse_args(argv)

    if not SITE_BASE.is_file():
        print(f"ОШИБКА: нет файла общих настроек {SITE_BASE}: общие настройки не обновлены.", file=sys.stderr)
        return 1
    if not args.config.is_file():
        print(f"ОШИБКА: нет файла {args.config}: общие настройки не обновлены.", file=sys.stderr)
        return 1
    base, _ = load(SITE_BASE)
    text, eol = load(args.config)
    updated = apply(text, render_block(base))
    try:
        tomllib.loads(updated)
    except tomllib.TOMLDecodeError as exc:
        print(f"ОШИБКА: после вставки общих настроек {args.config.name} — некорректный TOML ({exc}). Проверьте, что "
              f"ключи [project] стоят до блока ENGINE SETTINGS, а таблицы продукта не повторяют таблицы общих "
              f"настроек. Файл не изменён.", file=sys.stderr)
        return 1

    if updated == text:
        print("Общие настройки сайта без изменений.")
        return 0
    if args.check:
        print("Общие настройки сайта устарели: запустите python engine/py/site_settings.py", file=sys.stderr)
        return 1
    save(args.config, updated, eol)
    print(f"Общие настройки сайта обновлены: {args.config.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
