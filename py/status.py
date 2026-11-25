"""Статусы, значки и приоритеты фич (F) и подфункциональностей (SF) в метаданных index.md.

Запуск из корня репозитория продукта (в CI после слияния в main — общий workflow движка .github/workflows/build.yml):

    python engine/py/status.py              # обновить метаданные
    python engine/py/status.py --check      # только сверить: код возврата 1, если метаданные устарели

SF — папки sf-* внутри папки фичи (docs/requirements/features/<фича>/sf-*/index.md)
-----------------------------------------------------------------------------------
Статус SF аналитик вписывает вручную в строку `- **Статус**: …` (значение из SF_STATUSES: бэклог, анализ, готово
к разработке, разработка, реализовано, архив; регистр не важен). По нему скрипт записывает в метаданные:

* `icon` — значок в левом меню (STATUS_ICONS, например `lucide/file-pen-line`);
* `status` — русское название статуса (например, `"анализ"`): его выводит «паспорт» страницы (custom/passport.html).

Строки «Статус» нет или значение не из списка — ошибка: файл не меняется, код возврата 1 (в CI публикация не выполняется).

Приоритет SF аналитик вписывает вручную в строку `- **Приоритет**: …` (значение из PRIORITY_ORDER: must, should, could,
won't; регистр не важен). Скрипт записывает его в поле `priority` — первой строкой метаданных. Значение не из списка —
ошибка; строки нет — предупреждение, `priority` остаётся пустым (дашборд покажет SF в «Требует внимания»).

F — index.md папки фичи
-----------------------
Статус F не вписывают вручную: он вычисляется из статусов её SF по правилу Jira для эпиков
(common.feature_status):

* SF в архиве не учитываются; если в архиве все SF — F в архиве;
* все остальные SF в бэклоге — F «бэклог»;
* все остальные SF реализованы — F «реализовано»;
* иначе — F «в работе» (статус есть только у F, вручную его не вписывают).

Приоритет F тоже вычисляется: самый строгий приоритет среди её SF (must строже should и т. д.); SF в архиве не
учитываются, если есть другие. В тексте F строку «Приоритет» не ведут.

У фичи без SF метаданные не меняются. В index.md фичи скрипт обновляет `priority`, `status` (русское название:
«в работе», «реализовано»…) и `icon`, а также строку `- **Статус**: …`, если она в файле есть.

Все настройки — в py/config.py, обход реестра и правила вычисления — в py/common.py. Сторонние пакеты не нужны: только стандартная библиотека Python 3.10+.
"""

from __future__ import annotations

import argparse
import sys

from common import Feature, load, registry, rel, save, set_meta
from config import (ICON_KEY, PRIORITY_KEY, PRIORITY_ORDER, SF_STATUSES, STATUS_ICONS, STATUS_KEY, STATUS_LINE_RE)


def icon_of(status: str) -> str:
    """`:lucide-file-check:` → `lucide/file-check` (так значок записывается в поле `icon`)."""
    return "lucide/" + STATUS_ICONS[status].strip(":").removeprefix("lucide-")


def set_status_line(text: str, status: str) -> str:
    """Значение строки `- **Статус**: …` (если она есть)."""
    return STATUS_LINE_RE.sub(lambda m: m.group(0)[:m.start("status") - m.start()] + status, text, count=1)


def apply(text: str, status: str, priority: str | None, feature: bool) -> str:
    """`priority`, `status` и `icon` в метаданных; feature=True — index.md фичи: ещё и строка «Статус», если она есть."""
    text = set_meta(text, PRIORITY_KEY, priority or "", first=True)
    text = set_meta(text, STATUS_KEY, status)
    text = set_meta(text, ICON_KEY, icon_of(status), quote=False, after=STATUS_KEY)
    return set_status_line(text, status) if feature else text


def check(features: list[Feature], errors: list[str], warnings: list[str]) -> None:
    """Ошибки и предупреждения по строкам «Статус» и «Приоритет» в SF."""
    for f in features:
        for s in f.subs:
            if s.raw_status is None:
                errors.append(f"{rel(s.index)}: нет строки «- **Статус**: …»")
            elif s.status is None:
                errors.append(f"{rel(s.index)}: статус «{s.raw_status}» не из списка: {', '.join(SF_STATUSES)}")
            if s.raw_priority is None:
                warnings.append(f"{rel(s.index)}: нет строки «- **Приоритет**: …» (или она пустая)")
            elif s.priority is None:
                errors.append(f"{rel(s.index)}: приоритет «{s.raw_priority}» не из списка: {', '.join(PRIORITY_ORDER)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Статусы, значки и приоритеты F и SF в метаданных index.md.")
    parser.add_argument("--check", action="store_true", help="только сверить, файлы не изменяются")
    args = parser.parse_args(argv)

    errors: list[str] = []
    warnings: list[str] = []
    features = registry(warnings)
    check(features, errors, warnings)
    for message in warnings:
        print(f"Предупреждение: {message}")
    for message in errors:
        print(f"ОШИБКА: {message}", file=sys.stderr)
    if errors:
        print(f"Статусы не обновлены: ошибок — {len(errors)}.", file=sys.stderr)
        return 1

    updates: dict = {}                     # путь → (новый текст, конец строки)
    for f in features:
        targets = [(s.index, s.status, s.priority, False) for s in f.subs]
        if f.status:
            targets.append((f.index, f.status, f.priority, True))
            print(f"  {rel(f.index)}: {f.status}, приоритет {f.priority or '—'} (F, вычислены по {len(f.subs)} SF)")
        else:
            print(f"  {rel(f.index)}: нет SF со статусом — метаданные не меняются")
        for path, status, priority, is_feature in targets:
            text, eol = load(path)
            new = apply(text, status, priority, is_feature)
            if not is_feature:
                print(f"  {rel(path)}: {status}, приоритет {priority or '—'}")
            if new != text:
                updates[path] = (new, eol)

    if args.check:
        if updates:
            print(f"Статусы устарели в {len(updates)} файлах: запустите python engine/py/status.py", file=sys.stderr)
            return 1
        print("Статусы, значки и приоритеты актуальны.")
        return 0
    for path, (text, eol) in updates.items():
        save(path, text, eol)
        print(f"Обновлено: {rel(path)}")
    print(f"Статусы, значки и приоритеты: изменено файлов — {len(updates)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
