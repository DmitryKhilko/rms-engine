"""Дашборд реестра требований: блок на странице docs/requirements/features/index.md между маркерами
`<!-- BEGIN GENERATED DASHBOARD … -->` и `<!-- END GENERATED DASHBOARD -->`.

Запуск из корня репозитория продукта (в CI после слияния в main — общий workflow движка .github/workflows/build.yml):

    python engine/py/dashboard.py              # пересобрать дашборд и записать страницу, если изменилась
    python engine/py/dashboard.py --check      # только сверить: код возврата 1, если дашборд устарел

Что на дашборде (сверху вниз)
-----------------------------
1. «Статусы функциональностей» — свёрнутый блок с пояснениями к статусам.
2. «Прогресс по F» — полоса на каждую F: доля её SF в каждом статусе (архивные не учитываются), «реализовано X из N».
3. «Приоритет × статус SF» — сколько SF каждого приоритета в каждом статусе.
4. «Требует внимания» — проверки требований: SF без FR, FR без критериев приёмки, SF без приоритета, повторяющиеся коды,
   неподтверждённые вопросы и допущения, битые ссылки. Выводятся все замечания, каждое — со ссылкой на место
   в требованиях. Группа с замечаниями раскрыта, без замечаний — свёрнута («Замечаний нет»). Коды, вопросы,
   допущения и ссылки проверяются в папках ATTENTION_DIRS (глобальные требования и реестр), остальное — по SF реестра.
5. «Последние изменения» — последние записи журналов изменений всех разделов реестра.

Фичи, SF, их названия, статусы и приоритеты (у F — вычисленные) берёт common.registry() — тот же обход реестра, что
у status.py и nav.py, поэтому фичи идут в том же порядке, что в меню.
В блоке нет даты и времени: без изменений в требованиях страница не меняется и лишнего коммита нет.

Все настройки — в py/config.py (раздел «Дашборд реестра»), оформление — custom/css/extra.css (раздел 12).
Сторонние пакеты не нужны: только стандартная библиотека Python 3.10+.
"""

from __future__ import annotations

import argparse
import html
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from common import Feature, load, read, registry, rel, save, sf_title
from config import (ACCEPTANCE_MARK, ANCHOR_RE, ARCHIVED_STATUS, ATTENTION_DIRS, CHANGES_LIMIT, DASHBOARD_BEGIN,
                    DASHBOARD_END, DASHBOARD_PAGE, DASHBOARD_RE, DOCS_DIR, DONE_STATUS, FR_FILE, FR_HEADING_RE,
                    FEATURE_TITLE_RE, GLOBAL_SF_DIR, HEADING_ANCHOR_RE, INDEX_NAME, INLINE_LINK_RE, JOURNAL_ENTRY_RE, NOTE_FINAL,
                    NOTE_KINDS, NOTE_OWNER_RE, NOTE_RE, NOTE_STATUS_RE, PRIORITY_ORDER, REF_LINK_RE, REGISTRY_DIR,
                    REQUIREMENT_ID_RE, SF_STATUSES, STATUS_CSS, STATUS_DESCRIPTIONS, STATUS_ICONS)

H1_LINE_RE = re.compile(r"^#[ \t]+.+$", re.MULTILINE)
FENCE_RE = re.compile(r"^(```|~~~).*?^\1[ \t]*$", re.MULTILINE | re.DOTALL)
NO_PRIORITY = "не указан"


# ---------------------------------------------------------------------------
# Данные
# ---------------------------------------------------------------------------

def place(path: Path, features: list[Feature]) -> str:
    """Подпись файла для списков: «Фича → SF (файл)», «Глобальные требования → SF-G (файл)»."""
    global_root = DOCS_DIR / GLOBAL_SF_DIR
    if global_root in path.parents:
        top = path.relative_to(global_root).parts
        file = "" if path.name == INDEX_NAME else f" ({path.name})"
        if len(top) > 1:
            return f"Глобальные требования → {sf_title(global_root / top[0]) or top[0]}{file}"
        return f"Глобальные требования{file}"
    for f in features:
        if path.parent == f.folder:
            return f.title if path.name == INDEX_NAME else f"{f.title} ({path.name})"
        for s in f.subs:
            if s.folder in path.parents or path.parent == s.folder:
                return f"{f.title} → {s.title}" + ("" if path.name == INDEX_NAME else f" ({path.name})")
    return rel(path)


def group_places(names: list[str]) -> str:
    """«Фича → A», «Фича → B», «Фича» → «Фича; Фича → A, B» (без повторов названия фичи)."""
    groups: dict[str, list[str]] = {}
    for name in dict.fromkeys(names):
        feature, _, sub = name.partition(" → ")
        groups.setdefault(feature, [])
        if sub:
            groups[feature].append(sub)
    return "; ".join(f"{f} → {', '.join(subs)}" if subs else f for f, subs in groups.items())


# ---------------------------------------------------------------------------
# HTML-кусочки
# ---------------------------------------------------------------------------

def esc(text: str) -> str:
    return html.escape(text, quote=True)


def statuses_info() -> list[str]:
    rows = [f"- {STATUS_ICONS[s]} {s}: {STATUS_DESCRIPTIONS[s]}" for s in [*SF_STATUSES, "в работе"]]
    return ['<details class="info dash-info" markdown>', "<summary>Статусы функциональностей</summary>", "", *rows, "",
            "</details>", ""]


def feature_link(f: Feature) -> str:
    """Название фичи — ссылка Markdown на требование F в её index.md (раздел «## F-…. Название {#…}»)."""
    text = read(f.index)
    found = FEATURE_TITLE_RE.search(text)
    anchor = None
    if found:
        line_end = text.find("\n", found.start())
        heading = HEADING_ANCHOR_RE.search(text, found.start(), len(text) if line_end < 0 else line_end + 1)
        anchor = heading.group("id") if heading else None
    return link(f.index, anchor, f.title, as_code=False)


def progress_block(features: list[Feature]) -> list[str]:
    order = [s for s in SF_STATUSES if s != ARCHIVED_STATUS]
    rows = []
    for f in features:
        active = [s for s in f.subs if s.status and s.status != ARCHIVED_STATUS]
        counts = Counter(s.status for s in active)
        done = counts[DONE_STATUS]
        segments = "".join(f'<span class="dash-{STATUS_CSS[s]}" style="width:{counts[s] * 100 / len(active):.4g}%" '
                           f'title="{esc(s)}: {counts[s]}"></span>' for s in order if counts[s]) if active else ""
        info = f"{f.status} · {len(active)} SF" if f.status else "нет SF"
        rows.append(f'<div class="dash-progress__row" markdown="block"><div class="dash-progress__title" markdown="span">'
                    f'{feature_link(f)}<small>{esc(info)}</small></div><div class="dash-bar">{segments}</div>'
                    f'<div class="dash-progress__done">реализовано <b>{done} из {len(active)}</b></div></div>')
    legend = "".join(f'<span class="dash-{STATUS_CSS[s]}"><i></i>{esc(s)}</span>' for s in order)
    return ["## Прогресс по F {#dash-progress}", "",
            "Доля SF, включенных в F, в каждом статусе; SF в архиве не учитываются.", "",
            '<div class="dash-progress" markdown="block">' + "".join(rows) + "</div>", "",
            f'<div class="dash-legend">{legend}</div>', ""]


def matrix_block(features: list[Feature]) -> list[str]:
    subs = [s for f in features for s in f.subs if s.status]
    cells = Counter((s.priority or NO_PRIORITY, s.status) for s in subs)
    rows_keys = PRIORITY_ORDER + ([NO_PRIORITY] if any(not s.priority for s in subs) else [])
    head = "".join(f'<th class="dash-{STATUS_CSS[s]}"><i></i>{esc(s)}</th>' for s in SF_STATUSES)
    body = []
    for p in rows_keys:
        tds = "".join(f'<td class="dash-{STATUS_CSS[s]} is-value">{cells[(p, s)]}</td>' if cells[(p, s)]
                      else '<td class="is-empty">—</td>' for s in SF_STATUSES)
        total = sum(cells[(p, s)] for s in SF_STATUSES)
        body.append(f"<tr><th>{esc(p)}</th>{tds}<td><b>{total}</b></td></tr>")
    sums = "".join(f"<td>{sum(cells[(p, s)] for p in rows_keys)}</td>" for s in SF_STATUSES)
    body.append(f'<tr class="dash-sum"><th>Всего</th>{sums}<td>{len(subs)}</td></tr>')
    return ["## Приоритет × статус SF {#dash-priority}", "", "Число SF каждого приоритета в каждом статусе.", "",
            f'<table class="dash-matrix"><thead><tr><th>Приоритет</th>{head}<th>Всего</th></tr></thead>'
            f'<tbody>{"".join(body)}</tbody></table>', ""]


# ---------------------------------------------------------------------------
# «Требует внимания»
# ---------------------------------------------------------------------------

@dataclass
class Check:
    title: str
    items: list[str]          # строки списка (Markdown)
    count: int                # число замечаний (бейдж)
    ok_note: str = ""         # дополнение к «Замечаний нет»


def md(text: str) -> str:
    """Текст для строки списка Markdown: экранирование символов разметки."""
    return re.sub(r"([\\`*_\[\]<>|])", r"\\\1", text)


def link(path: Path, anchor: str | None, label: str, as_code: bool = True) -> str:
    """Ссылка Markdown на файл (и раздел) относительно страницы дашборда: Zensical сам пересчитает её в адрес."""
    target = os.path.relpath(path, (DOCS_DIR / DASHBOARD_PAGE).parent).replace(os.sep, "/")
    text = f"`{label}`" if as_code else md(label)
    return f"[{text}]({target}{'#' + anchor if anchor else ''})"


def anchor_before(text: str, pos: int) -> str | None:
    """Якорь ближайшего заголовка выше позиции pos (раздел, в котором стоит пункт)."""
    found = None
    for m in HEADING_ANCHOR_RE.finditer(text, 0, pos):
        found = m.group("id")
    return found


def attention_files() -> list[Path]:
    return sorted(p for d in ATTENTION_DIRS for p in (DOCS_DIR / d).rglob("*.md"))


def check_fr(features: list[Feature]) -> tuple[Check, Check]:
    no_fr: list[str] = []
    no_ac: list[str] = []
    no_ac_count = 0
    for f in features:
        for s in f.subs:
            path = s.folder / FR_FILE
            raw = read(path) if path.is_file() else ""
            text = FENCE_RE.sub(lambda m: m.group(0) if ACCEPTANCE_MARK in m.group(0) else "", raw)
            heads = list(FR_HEADING_RE.finditer(text))
            if not heads:
                no_fr.append(link(s.index, None, f"{f.title} → {s.title}", as_code=False))
                continue
            missing = []
            for i, h in enumerate(heads):
                block = text[h.end():heads[i + 1].start() if i + 1 < len(heads) else len(text)]
                if ACCEPTANCE_MARK not in block:
                    missing.append(link(path, anchor_before(text, h.end()), h.group("id")))
            if missing:
                no_ac.append(f"{md(f.title)} → {md(s.title)}: " + ", ".join(missing))
                no_ac_count += len(missing)
    return (Check("SF без функциональных требований (FR)", no_fr, len(no_fr)),
            Check("FR без критериев приёмки", no_ac, no_ac_count))


def check_priority(features: list[Feature]) -> Check:
    items = [link(s.index, None, f"{f.title} → {s.title}", as_code=False)
             for f in features for s in f.subs if not s.priority]
    return Check("SF без приоритета", items, len(items))


def check_codes(features: list[Feature]) -> Check:
    seen: dict[str, list[tuple[Path, str | None]]] = defaultdict(list)
    for path in attention_files():
        text = FENCE_RE.sub("", read(path))
        for m in REQUIREMENT_ID_RE.finditer(text):
            end = text.find("\n", m.end())
            seen[m.group("id")].append((path, anchor_before(text, len(text) if end < 0 else end)))
    items = []
    for rid, places in sorted(seen.items()):
        if len(places) > 1:
            where = ", ".join(link(p, a, place(p, features), as_code=False) for p, a in places)
            items.append(f"`{rid}` — в {len(places)} местах: {where}")
    return Check("Повторяющиеся коды", items, len(items))


def check_notes(features: list[Feature]) -> Check:
    items, total = [], 0
    for path in attention_files():
        text = read(path)
        for m in NOTE_RE.finditer(text):
            total += 1
            kind = m.group("kind")
            status = NOTE_STATUS_RE.search(m.group("body"))
            value = status.group("value").strip() if status else ""
            if value.lower() in NOTE_FINAL[kind]:
                continue
            owner = NOTE_OWNER_RE.search(m.group("body"))
            role = "подтверждает" if kind == "H" else "решает"
            who = f", {role}: {md(owner.group('value'))}" if owner and owner.group("value") else ""
            items.append(f"{link(path, anchor_before(text, m.start()), m.group('id'))} — {NOTE_KINDS[kind]}, "
                         f"статус «{md(value or 'не указан')}»{who} ({md(place(path, features))})")
    note = f"{total - len(items)} из {total} в финальном статусе" if total else ""
    return Check("Неподтверждённые вопросы и допущения", items, len(items), note)


def anchors_of(path: Path, cache: dict[Path, set[str]]) -> set[str]:
    if path not in cache:
        cache[path] = {m.group("id") or m.group("html") for m in ANCHOR_RE.finditer(read(path))} if path.is_file() else set()
    return cache[path]


def check_links(features: list[Feature]) -> Check:
    cache: dict[Path, set[str]] = {}
    items, total = [], 0
    for path in attention_files():
        text = FENCE_RE.sub("", read(path))
        found = [(m.group("label"), m.group("url"), m.start()) for m in REF_LINK_RE.finditer(text)]
        found += [("", m.group("url"), m.start()) for m in INLINE_LINK_RE.finditer(text)]
        for label, url, pos in sorted(found, key=lambda x: x[2]):
            if re.match(r"^[a-z][a-z0-9+.-]*:", url, re.IGNORECASE):     # http:, mailto: и т. п.
                continue
            target, _, anchor = url.partition("#")
            if target and not target.endswith(".md"):
                continue
            target_path = (path.parent / target).resolve() if target else path.resolve()
            if not target_path.is_file() or (anchor and anchor not in anchors_of(target_path, cache)):
                total += 1
                shown = f"`{md(label)}` → `{url}`" if label else f"`{url}`"
                items.append(f"{link(path, anchor_before(text, pos), place(path, features), as_code=False)}: {shown}")
    return Check("Битые ссылки (ведут на несуществующий файл или раздел)", items, total)


def attention_block(features: list[Feature]) -> list[str]:
    no_fr, no_ac = check_fr(features)
    checks = [no_fr, no_ac, check_priority(features), check_codes(features), check_notes(features),
              check_links(features)]
    bad = [c for c in checks if c.count]
    hint = f"Групп с замечаниями: {len(bad)}, замечаний: {sum(c.count for c in bad)}." if bad else "Замечаний нет."
    lines = ["## Требует внимания {#dash-attention}", "", hint, ""]
    for c in checks:
        if c.count:
            lines += [f'<details class="warning dash-check" open markdown>',
                      f'<summary>{esc(c.title)}<span class="dash-count">{c.count}</span></summary>', "",
                      *(f"- {i}" for i in c.items), "", "</details>", ""]
        else:
            note = f" · {esc(c.ok_note)}" if c.ok_note else ""
            lines += [f'<details class="success dash-check"><summary>{esc(c.title)}'
                      f'<span class="dash-ok">Замечаний нет{note}</span></summary></details>', ""]
    return lines


# ---------------------------------------------------------------------------
# «Последние изменения»
# ---------------------------------------------------------------------------

def changes_block(features: list[Feature]) -> list[str]:
    entries = []
    for path in sorted((DOCS_DIR / REGISTRY_DIR).rglob(INDEX_NAME)):
        for m in JOURNAL_ENTRY_RE.finditer(read(path)):
            fmt = "%d.%m.%Y %H:%M:%S" if m.group("when").count(":") == 2 else "%d.%m.%Y %H:%M"
            entries.append((datetime.strptime(m.group("when"), fmt), place(path, features), m))
    entries.sort(key=lambda e: e[0], reverse=True)
    if not entries:
        return ["## Последние изменения {#dash-changes}", "", "Записей в журналах изменений пока нет.", ""]
    rows = "".join(
        f'<tr><td class="dash-when">{e[0]:%d.%m.%Y %H:%M}</td><td>{esc(e[1])}</td>'
        f'<td><a href="{esc(e[2].group("url"))}" target="_blank" rel="noopener">{esc(e[2].group("version"))}</a></td>'
        f'<td>{esc(e[2].group("files") or "")}</td><td>{esc(e[2].group("author"))}</td></tr>'
        for e in entries[:CHANGES_LIMIT])
    return ["## Последние изменения {#dash-changes}", "",
            f"Последние записи журналов изменений всех разделов реестра; версия — ссылка на коммит.", "",
            '<table class="dash-changes"><thead><tr><th>Когда</th><th>Раздел</th><th>Версия</th><th>Файлы</th>'
            f'<th>Редактор</th></tr></thead><tbody>{rows}</tbody></table>', ""]


# ---------------------------------------------------------------------------
# Сборка и запись
# ---------------------------------------------------------------------------

def render(features: list[Feature]) -> str:
    lines = [DASHBOARD_BEGIN, "", *statuses_info(),
             *progress_block(features), *matrix_block(features), *attention_block(features), *changes_block(features),
             DASHBOARD_END]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Дашборд реестра требований на странице features/index.md.")
    parser.add_argument("--check", action="store_true", help="только сверить, файл не изменяется")
    args = parser.parse_args(argv)

    page = DOCS_DIR / DASHBOARD_PAGE
    if not page.is_file():
        print(f"ОШИБКА: нет страницы docs/{DASHBOARD_PAGE}: дашборд не обновлён.", file=sys.stderr)
        return 1
    warnings: list[str] = []
    block = render(registry(warnings))
    for message in warnings:
        print(f"Предупреждение: {message}")

    text, eol = load(page)
    if DASHBOARD_RE.search(text):
        updated = DASHBOARD_RE.sub(lambda _: block, text, count=1)
    else:
        h1 = H1_LINE_RE.search(text)
        at = h1.end() if h1 else 0
        updated = text[:at] + ("\n\n" if h1 else "") + block + "\n" + text[at:].lstrip("\n")

    if updated == text:
        print("Дашборд без изменений.")
        return 0
    if args.check:
        print("Дашборд устарел: запустите python engine/py/dashboard.py", file=sys.stderr)
        return 1
    save(page, updated, eol)
    print(f"Дашборд обновлён: docs/{DASHBOARD_PAGE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
