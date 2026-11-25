"""Общая логика скриптов движка rms-engine (py/): чтение и запись файлов, метаданные, обход реестра требований.

Модуль без настроек (они — в config.py) и без точки запуска: его импортируют changelog.py, status.py, nav.py
и dashboard.py.

* Файлы читаются и пишутся «как есть»: концы строк файла (LF или CRLF) сохраняются.
* set_meta — единственная функция записи поля в метаданные (YAML Front Matter).
* registry() — фичи (F) и их подфункциональности (SF) в том порядке, в каком они идут в меню: фичи по полю `order`
  их index.md, затем по имени папки; SF — по порядку словаря FOLDER_TITLES. Статус и приоритет F вычисляются здесь же.
* sf_title() — название SF из заголовка её index.md (для папок sf-* не из FOLDER_TITLES и глобальных
  функциональностей).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from config import (ARCHIVED_STATUS, BACKLOG_STATUS, DOCS_DIR, DONE_STATUS, FEATURE_TITLE_RE, FOLDER_TITLES,
                    FRONT_MATTER_RE, H1_RE, IN_PROGRESS_STATUS, INDEX_NAME, ORDER_KEY, PRIORITY_LINE_RE,
                    PRIORITY_ORDER, REGISTRY_DIR, SF_FOLDER_PREFIX, SF_STATUSES, SF_TITLE_RE, STATUS_LINE_RE)

ORDER_RE = re.compile(rf"^{re.escape(ORDER_KEY)}:[ \t]*['\"]?(?P<order>-?\d+)['\"]?[ \t]*(?:#.*)?$", re.MULTILINE)


# ---------------------------------------------------------------------------
# Файлы
# ---------------------------------------------------------------------------

def load(path: Path) -> tuple[str, str]:
    """Текст файла с концами строк LF и исходный конец строки файла ("\\n" или "\\r\\n")."""
    raw = path.read_bytes().decode("utf-8")
    return raw.replace("\r\n", "\n"), ("\r\n" if "\r\n" in raw else "\n")


def read(path: Path) -> str:
    """Текст файла с концами строк LF."""
    return load(path)[0]


def save(path: Path, text: str, eol: str = "\n") -> None:
    """Записывает текст (с концами строк LF) с концами строк eol."""
    path.write_text(text.replace("\n", eol), encoding="utf-8", newline="")


def rel(path: Path) -> str:
    """Путь относительно docs/ (для сообщений)."""
    return path.relative_to(DOCS_DIR).as_posix()


def dict_key(name: str, titles: dict[str, str]) -> tuple[int, str]:
    """Ключ сортировки: сначала по порядку словаря, затем — не вошедшие в словарь, по алфавиту."""
    keys = list(titles)
    return (keys.index(name), "") if name in titles else (len(keys), name.lower())


# ---------------------------------------------------------------------------
# Метаданные (YAML Front Matter)
# ---------------------------------------------------------------------------

def front_matter(text: str) -> str:
    """Содержимое блока метаданных (без строк `---`); пустая строка — блока нет."""
    match = FRONT_MATTER_RE.match(text)
    return match.group(1) if match else ""


def has_meta(text: str, key: str) -> bool:
    return re.search(rf"^{re.escape(key)}:", front_matter(text), re.MULTILINE) is not None


def yaml_str(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def set_meta(text: str, key: str, value: str, *, quote: bool = True, after: str | None = None,
             first: bool = False) -> str:
    """Поле `key` в метаданных: заменяет значение (комментарий в конце строки сохраняется) или добавляет строку —
    после поля `after`, в начало метаданных (first=True) или в конец. Текста без метаданных не меняет."""
    match = FRONT_MATTER_RE.match(text)
    if not match:
        return text
    block = match.group(1)
    written = yaml_str(value) if quote else value
    pattern = re.compile(rf"^({re.escape(key)}:[ \t]*)(\"(?:[^\"\\\n]|\\.)*\"|'[^'\n]*'|[^\s#\n]*)", re.MULTILINE)
    if pattern.search(block):
        block = pattern.sub(lambda m: m.group(1) + written, block, count=1)
    else:
        line = f"{key}: {written}\n"
        anchor = re.search(rf"^{re.escape(after)}:[^\n]*\n", block, re.MULTILINE) if after else None
        if anchor:
            block = block[:anchor.end()] + line + block[anchor.end():]
        else:
            block = line + block if first else block + line
    return text[:match.start(1)] + block + text[match.end(1):]


# ---------------------------------------------------------------------------
# Статус и приоритет
# ---------------------------------------------------------------------------

def _line_value(pattern: re.Pattern, group: str, text: str) -> str | None:
    """Значение строки «- **Поле**: …» в нижнем регистре, без лишних пробелов; None — строки нет или она пустая."""
    found = pattern.search(text)
    value = " ".join(found.group(group).lower().split()) if found else ""
    return value or None


def manual_status(text: str) -> str | None:
    return _line_value(STATUS_LINE_RE, "status", text)


def manual_priority(text: str) -> str | None:
    return _line_value(PRIORITY_LINE_RE, "priority", text)


def feature_status(statuses: list[str]) -> str:
    """Статус F по статусам её SF (правило Jira для эпиков; SF в архиве не учитываются)."""
    active = [s for s in statuses if s != ARCHIVED_STATUS]
    if not active:
        return ARCHIVED_STATUS
    if all(s == BACKLOG_STATUS for s in active):
        return BACKLOG_STATUS
    if all(s == DONE_STATUS for s in active):
        return DONE_STATUS
    return IN_PROGRESS_STATUS


def feature_priority(items: list[tuple[str, str | None]]) -> str | None:
    """Приоритет F: самый строгий среди SF (пары статус, приоритет); архивные SF — только если других нет."""
    active = [p for s, p in items if s != ARCHIVED_STATUS and p]
    pool = active or [p for _, p in items if p]
    return min(pool, key=PRIORITY_ORDER.index) if pool else None


# ---------------------------------------------------------------------------
# Реестр: фичи и их SF
# ---------------------------------------------------------------------------

@dataclass
class SubFeature:
    folder: Path
    title: str                       # название в меню (FOLDER_TITLES, иначе заголовок SF)
    raw_status: str | None           # как записано в строке «Статус» (нижний регистр); None — строки нет
    raw_priority: str | None         # как записано в строке «Приоритет»; None — строки нет

    @property
    def index(self) -> Path:
        return self.folder / INDEX_NAME

    @property
    def status(self) -> str | None:
        """Статус, если он из списка SF_STATUSES."""
        return self.raw_status if self.raw_status in SF_STATUSES else None

    @property
    def priority(self) -> str | None:
        """Приоритет, если он из списка PRIORITY_ORDER."""
        return self.raw_priority if self.raw_priority in PRIORITY_ORDER else None


@dataclass
class Feature:
    folder: Path
    title: str
    order: int | None
    subs: list[SubFeature] = field(default_factory=list)

    @property
    def index(self) -> Path:
        return self.folder / INDEX_NAME

    @property
    def known(self) -> list[SubFeature]:
        """SF с допустимым статусом."""
        return [s for s in self.subs if s.status]

    @property
    def status(self) -> str | None:
        """Вычисленный статус F; None — нет SF с допустимым статусом."""
        return feature_status([s.status for s in self.known]) if self.known else None

    @property
    def priority(self) -> str | None:
        """Вычисленный приоритет F (по SF с допустимым статусом)."""
        return feature_priority([(s.status, s.priority) for s in self.known]) if self.known else None


def feature_title(index: Path, warnings: list[str]) -> str:
    """Название фичи: текст после ID в заголовке F («## F-PT. Справочник видов изделий»), иначе заголовок первого
    уровня, иначе имя папки."""
    text = read(index)
    found = FEATURE_TITLE_RE.search(text)
    if found:
        return found.group("title")
    match = FRONT_MATTER_RE.match(text)
    h1 = H1_RE.search(text[match.end():] if match else text)
    title = h1.group("title") if h1 else index.parent.name
    warnings.append(f"{rel(index)}: нет заголовка «## F-…. Название фичи» — в меню «{title}»")
    return title


def sf_title(folder: Path) -> str | None:
    """Название SF: текст после ID в заголовке SF в index.md папки («## SF-G-PAG. Пагинация»); None — заголовка нет."""
    index = folder / INDEX_NAME
    found = SF_TITLE_RE.search(read(index)) if index.is_file() else None
    return found.group("title") if found else None


def feature_order(index: Path) -> int | None:
    found = ORDER_RE.search(front_matter(read(index)))
    return int(found.group("order")) if found else None


def registry(warnings: list[str]) -> list[Feature]:
    """Фичи реестра (подпапки REGISTRY_DIR с index.md) и их SF (подпапки sf-* с index.md) в порядке меню."""
    root = DOCS_DIR / REGISTRY_DIR
    if not root.is_dir():
        return []
    features = []
    for folder in (p for p in root.iterdir() if p.is_dir() and (p / INDEX_NAME).is_file()):
        feature = Feature(folder, feature_title(folder / INDEX_NAME, warnings), feature_order(folder / INDEX_NAME))
        subs = [p for p in folder.iterdir() if p.is_dir() and p.name.startswith(SF_FOLDER_PREFIX)
                and (p / INDEX_NAME).is_file()]
        for sf in sorted(subs, key=lambda p: dict_key(p.name, FOLDER_TITLES)):
            text = read(sf / INDEX_NAME)
            title = FOLDER_TITLES.get(sf.name) or sf_title(sf) or sf.name
            feature.subs.append(SubFeature(sf, title,
                                           manual_status(text), manual_priority(text)))
        features.append(feature)
    features.sort(key=lambda f: (f.order is None, f.order or 0, f.folder.name))
    return features
