"""Меню сайта: блок `nav = [...]` в zensical.toml между маркерами `# BEGIN GENERATED NAV` и `# END GENERATED NAV`.

Запуск из корня репозитория продукта (в CI после слияния в main — общий workflow движка .github/workflows/build.yml):

    python engine/py/nav.py              # собрать меню и записать в zensical.toml, если изменилось
    python engine/py/nav.py --check      # только сверить: код возврата 1, если меню устарело

Зачем
-----
Без явного `nav` Zensical строит меню по папкам и подписывает пункты именами папок (`sf-create`, `dr`). Скрипт задаёт
меню явно, с русскими названиями, и пересобирает его при каждом запуске: новая фича или подфункциональность появляется
в меню без ручной правки zensical.toml.

Как собирается меню (названия и порядок — py/config.py движка; настроек в репозитории продукта нет)
-----------------------------------------------------------------------------------------------
* Неизменная часть меню — список NAV (стандартная структура docs/): страниц, которых у продукта нет, в меню нет.
  Вместо элемента REGISTRY подставляется группа «Реестр требований», вместо GLOBAL_SF — группа «Глобальные
  функциональности» (папки GLOBAL_SF_DIR с приставкой GLOBAL_SF_PREFIX в порядке GLOBAL_SF_ORDER; название — текст
  после ID в заголовке SF их index.md; файлы внутри — по FILE_TITLES, как у подфункциональностей реестра).
* Группа реестра: индекс папки REGISTRY_DIR, затем фичи — подпапки с index.md, по полю `order` их index.md, затем по
  имени папки. Название фичи — текст после ID в заголовке F в её index.md («## F-PT. Справочник видов изделий»;
  запасные варианты — заголовок первого уровня, имя папки).
* Внутри фичи: index.md (открывается щелчком на группе), затем файлы фичи (FILE_TITLES с приставкой
  FEATURE_FILE_PREFIX: «Общие UC», «Общие DR»…), затем подпапки (FOLDER_TITLES: «Список», «Создание»…;
  папка sf-* не из словаря — по заголовку SF её index.md).
* Внутри подпапки: index.md, затем файлы (FILE_TITLES: «DR», «FR»…) и вложенные подпапки по тем же правилам.
  Подпапка, в которой только index.md, — отдельная страница, а не группа. Папки без .md-файлов (например, api/)
  пропускаются.

Перед записью скрипт проверяет, что zensical.toml после замены остаётся корректным TOML; иначе файл не меняется.
Сторонние пакеты не нужны: только стандартная библиотека Python 3.11+ (модуль tomllib).
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path

from common import dict_key, registry, rel, sf_title
from config import (DOCS_DIR, FEATURE_FILE_PREFIX, FILE_TITLES, FOLDER_TITLES, GLOBAL_SF, GLOBAL_SF_DIR,
                    GLOBAL_SF_ORDER, GLOBAL_SF_PREFIX, GLOBAL_SF_TITLE, INDEX_NAME, NAV, NAV_BEGIN, NAV_END, NAV_RE,
                    REGISTRY, REGISTRY_DIR, REGISTRY_TITLE, ZENSICAL_CONFIG)


# ---------------------------------------------------------------------------
# Сборка дерева меню
# ---------------------------------------------------------------------------
# Узел меню: "путь.md" — индекс группы; (название, "путь.md") — страница; (название, [узлы]) — группа.

def has_pages(folder: Path) -> bool:
    return any(folder.rglob("*.md"))


def folder_items(folder: Path, file_prefix: str, warnings: list[str]) -> list:
    """Содержимое папки: index.md, файлы (FILE_TITLES), подпапки (FOLDER_TITLES)."""
    items: list = []
    if (folder / INDEX_NAME).is_file():
        items.append(rel(folder / INDEX_NAME))
    files = [p for p in folder.glob("*.md") if p.name != INDEX_NAME]
    for path in sorted(files, key=lambda p: dict_key(p.name, FILE_TITLES)):
        if path.name not in FILE_TITLES:
            warnings.append(f"{rel(path)}: файла нет в словаре FILE_TITLES движка — в меню «{path.name}»")
        items.append((file_prefix + FILE_TITLES.get(path.name, path.name), rel(path)))
    subfolders = [p for p in folder.iterdir() if p.is_dir() and has_pages(p)]
    for sub in sorted(subfolders, key=lambda p: dict_key(p.name, FOLDER_TITLES)):
        title = FOLDER_TITLES.get(sub.name) or sf_title(sub)
        if not title:
            title = sub.name
            warnings.append(f"{rel(sub)}/: папки нет в словаре FOLDER_TITLES движка и нет заголовка «## SF-…. Название»"
                            f" в её {INDEX_NAME} — в меню «{sub.name}»")
        children = folder_items(sub, "", warnings)
        # Только index.md — отдельная страница; иначе группа, которую открывает её index.md
        items.append((title, children[0]) if children == [rel(sub / INDEX_NAME)] else (title, children))
    return items


def registry_group(warnings: list[str]) -> tuple[str, list]:
    """Группа «Реестр требований»: индекс папки реестра, затем фичи в порядке common.registry()."""
    root = DOCS_DIR / REGISTRY_DIR
    items: list = []
    if (root / INDEX_NAME).is_file():
        items.append(rel(root / INDEX_NAME))
    for feature in registry(warnings):
        items.append((feature.title, folder_items(feature.folder, FEATURE_FILE_PREFIX, warnings)))
    if root.is_dir():
        for folder in (p for p in root.iterdir() if p.is_dir() and not (p / INDEX_NAME).is_file() and has_pages(p)):
            warnings.append(f"{rel(folder)}/: в папке фичи нет {INDEX_NAME} — фича в меню не попала")
    return REGISTRY_TITLE, items


def global_sf_group(warnings: list[str]) -> tuple[str, list]:
    """Группа «Глобальные функциональности»: папки GLOBAL_SF_DIR с приставкой GLOBAL_SF_PREFIX и index.md."""
    root = DOCS_DIR / GLOBAL_SF_DIR
    folders = [p for p in root.glob(GLOBAL_SF_PREFIX + "*") if p.is_dir() and (p / INDEX_NAME).is_file()]
    items: list = []
    order = {name: i for i, name in enumerate(GLOBAL_SF_ORDER)}
    for folder in sorted(folders, key=lambda p: (order.get(p.name, len(order)), p.name)):
        title = sf_title(folder)
        if not title:
            title = folder.name
            warnings.append(f"{rel(folder)}/{INDEX_NAME}: нет заголовка «## SF-G-…. Название» — в меню «{folder.name}»")
        children = folder_items(folder, "", warnings)
        items.append((title, children[0]) if children == [rel(folder / INDEX_NAME)] else (title, children))
    return GLOBAL_SF_TITLE, items


def expand(items: list, warnings: list[str]) -> list:
    """Неизменная часть меню (NAV) с группами на местах REGISTRY и GLOBAL_SF; страниц, которых нет, в меню нет."""
    result: list = []
    for item in items:
        if item == REGISTRY:
            title, children = registry_group(warnings)
            if children:
                result.append((title, children))
        elif item == GLOBAL_SF:
            title, children = global_sf_group(warnings)
            if children:
                result.append((title, children))
        elif isinstance(item, str):
            if (DOCS_DIR / item).is_file():
                result.append(item)
        else:
            title, value = item
            if isinstance(value, list):
                children = expand(value, warnings)
                if children:
                    result.append((title, children))
            elif (DOCS_DIR / value).is_file():
                result.append((title, value))
    return result


# ---------------------------------------------------------------------------
# TOML
# ---------------------------------------------------------------------------

def toml_str(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)   # строка JSON — корректная базовая строка TOML


def render(items: list, indent: int) -> list[str]:
    pad = " " * indent
    lines = []
    for item in items:
        if isinstance(item, str):
            lines.append(f"{pad}{toml_str(item)},")
        elif isinstance(item[1], str):
            lines.append(f"{pad}{{ {toml_str(item[0])} = {toml_str(item[1])} }},")
        else:
            lines.append(f"{pad}{{ {toml_str(item[0])} = [")
            lines += render(item[1], indent + 4)
            lines.append(f"{pad}] }},")
    return lines


def render_nav(items: list) -> str:
    return "\n".join(["nav = [", *render(items, 4), "]"])


# ---------------------------------------------------------------------------
# Запуск
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Меню сайта (nav) в zensical.toml по папкам docs/.")
    parser.add_argument("--config", type=Path, default=ZENSICAL_CONFIG, help="zensical.toml с маркерами меню")
    parser.add_argument("--check", action="store_true", help="только сверить, файл не изменяется")
    args = parser.parse_args(argv)

    text = args.config.read_bytes().decode("utf-8")      # как есть, без перевода концов строк
    eol = "\r\n" if "\r\n" in text else "\n"
    if not NAV_RE.search(text):
        print(f"ОШИБКА: {args.config.name}: нет маркеров «{NAV_BEGIN}» … «{NAV_END}»: меню не обновлено.",
              file=sys.stderr)
        return 1
    warnings: list[str] = []
    block = eol.join([NAV_BEGIN, *render_nav(expand(NAV, warnings)).split("\n"), NAV_END])
    updated = NAV_RE.sub(lambda _: block, text, count=1)
    for message in warnings:
        print(f"Предупреждение: {message}")
    try:
        tomllib.loads(updated)
    except tomllib.TOMLDecodeError as exc:
        print(f"ОШИБКА: после замены меню {args.config.name} — некорректный TOML ({exc}): файл не изменён.",
              file=sys.stderr)
        return 1

    if updated == text:
        print("Меню (nav) без изменений.")
        return 0
    if args.check:
        print("Меню (nav) устарело: запустите python engine/py/nav.py", file=sys.stderr)
        return 1
    args.config.write_text(updated, encoding="utf-8", newline="")
    print("Меню (nav) обновлено.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
