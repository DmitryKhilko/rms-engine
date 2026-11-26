"""Следующая версия движка rms-engine по коммитам после последнего выпуска (Conventional Commits).

Запускает workflow движка .github/workflows/release.yml после каждого push в main; вручную — для проверки:

    python py/release.py            # версия и описание выпуска (ничего не меняет)

Правила (те же, что у версий разделов в продуктах, py/changelog.py):

* `feat!:` / `fix!:` (восклицательный знак перед двоеточием) или `BREAKING CHANGE` в тексте коммита — новая линейка:
  v1.04.02 → v2.00.00. Продукты на `@v1` её не получают, пока сами не перейдут на `@v2`;
* `feat:` — новая возможность: v1.04.02 → v1.05.00;
* остальные коммиты (`fix:`, `docs:`, `refactor:`, без префикса…) — исправление: v1.04.02 → v1.04.03;
* `draft:` — черновик, выпуска не даёт. Если после последнего выпуска только черновики — выпуска нет.

Формат тега — vX.YY.ZZ, как у версий разделов: YY и ZZ — две цифры (v1.03.00). Последний выпуск — наибольший тег
вида vX.Y.Z по числам (старые теги без ведущих нулей, например v1.2.5, тоже учитываются); тегов нет — первый выпуск
v1.00.00.

Вывод (для GitHub Actions — в файл из переменной GITHUB_OUTPUT, иначе на экран):
    version=v1.05.00   точный тег выпуска (пусто — выпуска нет)
    major=v1           плавающий тег линейки
и описание выпуска (список коммитов по группам) — в файл release-notes.md.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
HEADER_RE = re.compile(r"^(?P<type>[a-zA-Z]+)(?:\([^)]*\))?(?P<bang>!)?:[ \t]*(?P<text>.*)$")
DRAFT_TYPE = "draft"
NOTES_FILE = Path("release-notes.md")
GROUPS = [("major", "Несовместимые изменения (нужны правки в продуктах)"), ("minor", "Новые возможности"),
          ("patch", "Исправления и прочее")]


def git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True, encoding="utf-8").stdout


def last_release() -> tuple[str | None, tuple[int, int, int]]:
    tags = [(tuple(map(int, m.groups())), t) for t in git("tag", "--list", "v*").split()
            if (m := TAG_RE.match(t))]
    if not tags:
        return None, (0, 0, 0)
    version, tag = max(tags)
    return tag, version


def commits(since: str | None) -> list[tuple[str, str, str]]:
    """(короткий хеш, заголовок, текст) коммитов после выпуска since, от старых к новым, без слияний."""
    rng = [f"{since}..HEAD"] if since else ["HEAD"]
    out = git("log", "--reverse", "--no-merges", "--format=%h%x1f%s%x1f%b%x1e", *rng)
    return [tuple(part.strip() for part in rec.split("\x1f")) for rec in out.split("\x1e") if rec.strip()]


def level(subject: str, body: str) -> str | None:
    """major / minor / patch; None — черновик."""
    m = HEADER_RE.match(subject)
    kind = m.group("type").lower() if m else ""
    if kind == DRAFT_TYPE:
        return None
    if (m and m.group("bang")) or "BREAKING CHANGE" in body:
        return "major"
    return "minor" if kind == "feat" else "patch"


def main() -> int:
    tag, (x, y, z) = last_release()
    found = [(h, s, level(s, b)) for h, s, b in commits(tag)]
    found = [c for c in found if c[2]]
    if not found:
        version = ""
        print(f"Выпуска нет: после {tag or 'начала истории'} нет новых коммитов (черновики не считаются).")
    else:
        levels = {c[2] for c in found}
        if not tag:
            x, y, z = 1, 0, 0
        elif "major" in levels:
            x, y, z = x + 1, 0, 0
        elif "minor" in levels:
            x, y, z = x, y + 1, 0
        else:
            x, y, z = x, y, z + 1
        version = f"v{x}.{y:02d}.{z:02d}"
        lines = []
        for key, title in GROUPS:
            items = [f"- {s} ({h})" for h, s, lv in found if lv == key]
            if items:
                lines += [f"### {title}", "", *items, ""]
        NOTES_FILE.write_text("\n".join(lines), encoding="utf-8")
        print(f"Выпуск {version} (предыдущий — {tag or 'нет'}), коммитов: {len(found)}.")
        print(NOTES_FILE.read_text(encoding="utf-8"))

    result = f"version={version}\nmajor={f'v{x}' if version else ''}\n"
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as fh:
            fh.write(result)
    else:
        print(result, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
