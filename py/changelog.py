"""Версии и «Журнал изменений» разделов требований по истории git.

Запуск из корня репозитория продукта (в CI после слияния в main — общий workflow движка .github/workflows/build.yml):

    python engine/py/changelog.py              # пересчитать и записать изменения
    python engine/py/changelog.py --dry-run    # только отчёт, файлы не меняются
    python engine/py/changelog.py --check      # только сверить: код возврата 1, если версии или журналы устарели

Где ведётся журнал
------------------
Только в файлах `index.md` внутри `docs/`, в которых есть заголовок журнала:

    ## Журнал изменений {#change-history .collapsed}

Такой `index.md` отвечает за свою папку: в его журнал попадают коммиты, изменившие любой файл этой папки (`.md`, `.json`,
картинки…) и её подпапок, кроме подпапок, у которых есть собственный `index.md` с журналом. Например:

* `sf-create/index.md` — все файлы `sf-create/`, включая `sf-create/api/*.json`;
* `dict-product-type/index.md` — только файлы, лежащие прямо в `dict-product-type/` (`fr.md`, `uc.md`, …): подпапки
  `sf-*` ведут свои журналы.

В остальных файлах журнал не ведётся: заголовок журнала в них скрипт не трогает и выводит предупреждение.

Как считается версия X.YY.ZZ (Conventional Commits)
---------------------------------------------------
Коммиты папки перебираются от старых к новым, начальная версия — 0.00.00:

* первый коммит папки — создание раздела: версия остаётся 0.00.00, записи в журнале нет;
* коммит с пометкой `[skip ci]` (автоматический коммит CI) и коммит с префиксом `draft:` пропускаются;
* `feat!:` (или `BREAKING CHANGE` в тексте сообщения) — X+1, YY=0, ZZ=0;
* `feat:` — YY+1, ZZ=0;
* всё остальное (`fix:`, `docs:`, сообщение без префикса и т. п.) — ZZ+1.

Коммит, изменивший несколько файлов папки, повышает версию один раз.

Что записывается в index.md
---------------------------
1. Раздел «Журнал изменений» перезаписывается целиком: по строке на каждую версию, новые сверху:

       - [Версия 0.01.00 (04.11.2026 07:44:15; dr.md)](<repo_url>/commit/<sha>){target="_blank" rel="noopener"}. Редактор: Автор

   В скобках после даты — файлы раздела, изменённые коммитом (пути относительно папки index.md, через запятую).
   Адрес репозитория — `repo_url` из zensical.toml. Записей нет — строка «- Записей пока нет.».
2. Если в метаданных (YAML Front Matter) есть поле `version`, обновляются `version`, `version_datetime`
   (ДД.ММ.ГГГГ ЧЧ:ММ:СС) и `editor` (автор коммита, давшего текущую версию); их выводит «паспорт» страницы
   (custom/passport.html). Поля `version` нет — обновляется только журнал. Концы строк файла (LF или CRLF) сохраняются.

Полная перезапись выбрана намеренно: журнал всегда повторяет историю git, без дублей и сбоев порядка.
Для этого нужна полная история репозитория (в CI — checkout с `fetch-depth: 0`).
Если переименовать или перенести саму папку раздела, история до переноса в версию не попадёт.
Настройки (названия полей, формат даты, подписи) — в py/config.py.
Сторонние пакеты не нужны: только стандартная библиотека Python 3.10+ и git.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from common import has_meta, load, read, save, set_meta
from config import (CHANGELOG_EMPTY, CHANGELOG_HEADING_RE, CHANGELOG_TITLE, COMMIT_URL_PATH, CONVENTIONAL_RE,
                    DATETIME_FORMAT, DATETIME_KEY, DEFAULT_VERSION, DOCS_DIR, DRAFT_TYPE, EDITOR_KEY, ENTRY_AUTHOR_LABEL,
                    FILES_SEPARATOR, GENERATED_COMMIT_MARK, INDEX_NAME, REPO_URL_RE, VERSION_KEY, ZENSICAL_CONFIG)

SEP = "\x1f"


# ---------------------------------------------------------------------------
# git
# ---------------------------------------------------------------------------

def git(root: Path, *args: str) -> str | None:
    """Вывод команды git (UTF-8) или None, если git недоступен или команда завершилась ошибкой."""
    try:
        done = subprocess.run(["git", "-c", "core.quotepath=false", *args], cwd=root, capture_output=True, check=False)
    except (OSError, ValueError):
        return None
    return done.stdout.decode("utf-8", errors="replace") if done.returncode == 0 else None


def repo_url(config: Path) -> str:
    """`repo_url` из zensical.toml без завершающего «/»; пустая строка, если не задан."""
    try:
        found = REPO_URL_RE.search(config.read_text(encoding="utf-8"))
    except OSError:
        return ""
    return found.group(1).rstrip("/") if found else ""


# ---------------------------------------------------------------------------
# Версии по истории коммитов
# ---------------------------------------------------------------------------

@dataclass
class Entry:
    version: str
    commit: str
    author: str
    when: str
    files: list[str] = field(default_factory=list)   # изменённые файлы раздела, пути относительно папки index.md


@dataclass
class History:
    commits: int = 0                                         # коммиты папки без автоматических
    entries: list[Entry] = field(default_factory=list)      # от старых к новым


def next_version(version: tuple[int, int, int], message: str) -> tuple[int, int, int]:
    major, minor, patch = version
    found = CONVENTIONAL_RE.match(message.strip().split("\n", 1)[0])
    if (found and found.group("bang")) or "BREAKING CHANGE" in message:
        return major + 1, 0, 0
    if found and found.group("type").lower() == "feat":
        return major, minor + 1, 0
    return major, minor, patch + 1


def is_draft(message: str) -> bool:
    found = CONVENTIONAL_RE.match(message.strip().split("\n", 1)[0])
    return bool(found) and found.group("type").lower() == DRAFT_TYPE


def format_version(version: tuple[int, int, int]) -> str:
    return f"{version[0]}.{version[1]:02d}.{version[2]:02d}"


def scope_history(root: Path, folder: str, excluded: list[str]) -> History:
    """История папки раздела (без подпапок из `excluded`): первый коммит — создание, каждый следующий
    (кроме `[skip ci]` и `draft:`) — новая версия."""
    pathspecs = [f"{folder}/", *(f":(exclude){sub}/" for sub in excluded)]
    # --name-only с теми же путями выводит после сообщения (за разделителем %x1e) только файлы раздела
    out = git(root, "log", "--reverse", "--no-merges", "--name-only", f"--date=format:{DATETIME_FORMAT}",
              f"--format=%x00%H{SEP}%an{SEP}%ad{SEP}%B%x1e", "--", *pathspecs)
    history = History()
    if not out:
        return history
    version = tuple(int(p) for p in DEFAULT_VERSION.split("."))
    for chunk in out.split("\x00")[1:]:
        record, _, names = chunk.partition("\x1e")
        commit, author, when, message = (record.split(SEP, 3) + ["", "", ""])[:4]
        files = [PurePosixPath(n).relative_to(folder).as_posix() for n in names.split("\n")
                 if n.strip() and n.startswith(folder + "/")]
        if GENERATED_COMMIT_MARK in message:
            continue
        history.commits += 1
        if history.commits == 1 or is_draft(message):
            continue
        version = next_version(version, message)
        history.entries.append(Entry(format_version(version), commit.strip(), author.strip(), when.strip(), files))
    return history


# ---------------------------------------------------------------------------
# Изменение текста файла
# ---------------------------------------------------------------------------

def has_journal(text: str) -> bool:
    return any(CHANGELOG_HEADING_RE.match(line) for line in text.replace("\r\n", "\n").split("\n"))


def build_journal(entries: list[Entry], url: str) -> list[str]:
    """Строки списка журнала (без заголовка), новые версии сверху."""
    lines = []
    for item in reversed(entries):
        details = "; ".join(part for part in (item.when, FILES_SEPARATOR.join(item.files)) if part)
        label = f"Версия {item.version} ({details})" if details else f"Версия {item.version}"
        link = f'[{label}]({url}{COMMIT_URL_PATH}{item.commit}){{target="_blank" rel="noopener"}}' if url else label
        lines.append(f"- {link}. {ENTRY_AUTHOR_LABEL}: {item.author}")
    return lines or [f"- {CHANGELOG_EMPTY}"]


def replace_journal(lines: list[str], journal: list[str]) -> list[str] | None:
    """Заменяет содержимое раздела журнала. Раздел — заголовок и следующие за ним пустые строки, пункты списка
    и строки с отступом, а также строка «Записей пока нет.» без маркера (остаток ручной правки); первая иная строка
    (следующий заголовок, абзац, определение ссылки) — уже не журнал.
    None — заголовка в файле нет."""
    start = next((i for i, line in enumerate(lines) if CHANGELOG_HEADING_RE.match(line)), None)
    if start is None:
        return None
    end = start + 1
    while end < len(lines) and (not lines[end].strip() or lines[end].startswith(("- ", "* ", " ", "\t"))
                                or lines[end].strip() == CHANGELOG_EMPTY):   # «Записей пока нет.» без маркера
        end += 1
    tail = lines[end:]
    return lines[:start + 1] + [""] + journal + ([""] if tail else []) + tail


def apply(text: str, history: History, url: str) -> str | None:
    """Текст index.md (концы строк LF) с актуальным журналом и метаданными версии; None — в файле нет заголовка журнала."""
    if has_meta(text, VERSION_KEY):
        last = history.entries[-1] if history.entries else None
        text = set_meta(text, VERSION_KEY, last.version if last else DEFAULT_VERSION)
        text = set_meta(text, DATETIME_KEY, last.when if last else "")
        if last:
            text = set_meta(text, EDITOR_KEY, last.author)
    lines = replace_journal(text.split("\n"), build_journal(history.entries, url))
    return None if lines is None else "\n".join(lines)


# ---------------------------------------------------------------------------
# Запуск
# ---------------------------------------------------------------------------

def sync(docs_dir: Path, config: Path, dry_run: bool, check: bool) -> int:
    root_out = git(docs_dir, "rev-parse", "--show-toplevel")
    if not root_out:
        print("Журналы не обновлены: папка не входит в git-репозиторий.", file=sys.stderr)
        return 1
    root = Path(root_out.strip())
    if (git(root, "rev-parse", "--is-shallow-repository") or "").strip() == "true":
        print("ВНИМАНИЕ: неполная история (shallow clone) — версии будут посчитаны неверно. "
              "В CI нужен checkout с fetch-depth: 0.")
    url = repo_url(config)
    if not url:
        print("repo_url в zensical.toml не задан: версии в журнале будут без ссылок на коммиты.")

    docs_rel = docs_dir.resolve().relative_to(root).as_posix()
    tracked = sorted(p for p in (git(root, "ls-files", "-z", "--", docs_rel) or "").split("\0")
                     if p.endswith(".md") and (root / p).is_file())

    # Папки разделов: папка index.md с заголовком журнала
    owners: dict[str, str] = {}             # папка → путь к её index.md
    for rel in tracked:
        if not has_journal(read(root / rel)):
            continue
        path = PurePosixPath(rel)
        if path.name == INDEX_NAME:
            owners[path.parent.as_posix()] = rel
        else:
            print(f"Предупреждение: {rel}: журнал ведётся только в {INDEX_NAME} папки — "
                  f"раздел «{CHANGELOG_TITLE}» в этом файле не обновляется, его можно удалить.")

    processed, changed = 0, []
    for folder, rel in sorted(owners.items()):
        # Подпапки с собственным журналом исключаются из истории раздела (вложенные в них — тоже, вместе с ними)
        excluded = [f for f in owners if f != folder and f.startswith(folder + "/")]
        excluded = [f for f in excluded if not any(f.startswith(e + "/") for e in excluded)]
        history = scope_history(root, folder, excluded)
        path = root / rel
        text, eol = load(path)
        updated = apply(text, history, url)
        if updated is None:
            continue
        processed += 1
        version = history.entries[-1].version if history.entries else DEFAULT_VERSION
        mark = "изменён" if updated != text else "без изменений"
        print(f"  {rel}: версия {version}, коммитов {history.commits}, записей журнала {len(history.entries)} — {mark}")
        if updated != text:
            changed.append(rel)
            if not (dry_run or check):
                save(path, updated, eol)
    action = "был бы изменён" if dry_run or check else "изменено"
    print(f"Разделов с журналом изменений: {processed}, {action}: {len(changed)}.")
    if check and changed:
        print("Версии и журналы устарели: запустите python engine/py/changelog.py", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Версии и «Журнал изменений» разделов требований по истории git.")
    parser.add_argument("--docs", type=Path, default=DOCS_DIR, help="папка с исходниками сайта (по умолчанию docs/)")
    parser.add_argument("--config", type=Path, default=ZENSICAL_CONFIG, help="файл с repo_url (zensical.toml)")
    parser.add_argument("--dry-run", action="store_true", help="только отчёт, файлы не изменяются")
    parser.add_argument("--check", action="store_true",
                        help="только сверить, файлы не изменяются: код возврата 1, если версии или журналы устарели")
    args = parser.parse_args(argv)
    if not args.docs.is_dir():
        print(f"Папка не найдена: {args.docs}", file=sys.stderr)
        return 1
    return sync(args.docs.resolve(), args.config, args.dry_run, args.check)


if __name__ == "__main__":
    sys.exit(main())
