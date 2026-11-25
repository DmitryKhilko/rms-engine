"""Настройки движка rms-engine: пути, названия, словари, маркеры и регулярные выражения.

Файл не содержит логики: скрипты (changelog.py, status.py, nav.py, dashboard.py) берут отсюда все значения, которые
может понадобиться поменять.

Значения в этом файле — общие для всех продуктов предприятия (стандарт). То, что у каждого продукта своё, — неизменная
часть меню, папки реестра и страница дашборда, названия папок и файлов в меню, глобальные функциональности, — продукт
задаёт в файле rms.toml в корне своего репозитория (см. раздел «Настройки продукта» в конце файла и README движка).

Скрипты запускаются из корня репозитория продукта (python engine/py/<скрипт>.py): корень продукта — текущая папка
или папка из переменной окружения RMS_PRODUCT_ROOT.
"""

from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path

# ---------------------------------------------------------------------------
# Пути (репозиторий продукта)
# ---------------------------------------------------------------------------
REPO_ROOT = Path(os.environ.get("RMS_PRODUCT_ROOT") or Path.cwd()).resolve()   # корень репозитория продукта
PRODUCT_SETTINGS = REPO_ROOT / "rms.toml"            # настройки продукта (необязательный файл)
ENGINE_ROOT = Path(__file__).resolve().parents[1]    # корень движка (py/config.py → ..)
DOCS_DIR = REPO_ROOT / "docs"                        # исходники сайта
ZENSICAL_CONFIG = REPO_ROOT / "zensical.toml"        # настройки сайта: repo_url, блок меню
INDEX_NAME = "index.md"                              # индекс папки

FRONT_MATTER_RE = re.compile(r"\A---[ \t]*\n(.*?\n)---[ \t]*(?:\n|\Z)", re.DOTALL)


# ===========================================================================
# ВЕРСИИ И ЖУРНАЛ ИЗМЕНЕНИЙ (changelog.py)
# ===========================================================================
# Журнал ведётся только в index.md с заголовком журнала; такой index.md отвечает за свою папку и подпапки без
# собственного журнала. Версия X.YY.ZZ считается по сообщениям коммитов (Conventional Commits). Подробнее — changelog.py.

CHANGELOG_TITLE = "Журнал изменений"
CHANGELOG_ANCHOR = "change-history"
CHANGELOG_EMPTY = "Записей пока нет."
ENTRY_AUTHOR_LABEL = "Редактор"
FILES_SEPARATOR = ", "                  # между изменёнными файлами в записи журнала
COMMIT_URL_PATH = "/commit/"            # одинаково для GitHub и Gitea

# Метаданные версии в Front Matter index.md; обновляются, только если в нём есть поле VERSION_KEY
VERSION_KEY = "version"                 # версия раздела
DATETIME_KEY = "version_datetime"       # дата и время коммита, давшего текущую версию
EDITOR_KEY = "editor"                   # автор этого коммита

DEFAULT_VERSION = "0.00.00"
DATETIME_FORMAT = "%d.%m.%Y %H:%M:%S"   # для git: --date=format:... (ДД.ММ.ГГГГ ЧЧ:ММ:СС)
DRAFT_TYPE = "draft"                    # префикс коммита: версия и журнал не меняются
GENERATED_COMMIT_MARK = "[skip ci]"     # пометка автоматических коммитов CI: в версиях не учитываются

CHANGELOG_HEADING_RE = re.compile(
    rf"^##[ \t]+{re.escape(CHANGELOG_TITLE)}[ \t]*\{{#{CHANGELOG_ANCHOR}(?:[ \t][^}}]*)?\}}[ \t]*$")
CONVENTIONAL_RE = re.compile(r"^(?P<type>[A-Za-z]+)(\([^)\n]*\))?(?P<bang>!)?:[ \t]*\S")
REPO_URL_RE = re.compile(r'^repo_url\s*=\s*"([^"]+)"', re.MULTILINE)


# ===========================================================================
# ОБЩИЕ НАСТРОЙКИ САЙТА (site_settings.py)
# ===========================================================================
# Тема и расширения Markdown общие для всех продуктов: файл SITE_BASE движка. site_settings.py переписывает им блок
# между маркерами SITE_BEGIN и SITE_END в zensical.toml продукта (нет маркеров — добавляет блок после меню).

SITE_BASE = ENGINE_ROOT / "zensical.base.toml"
SITE_BEGIN = "# BEGIN ENGINE SETTINGS — общие настройки движка rms-engine, вручную не редактируйте"
SITE_BEGIN_PREFIX = "# BEGIN ENGINE SETTINGS"
SITE_END = "# END ENGINE SETTINGS"
SITE_RE = re.compile(re.escape(SITE_BEGIN_PREFIX) + r"[^\n]*\n.*?" + re.escape(SITE_END), re.DOTALL)


# ===========================================================================
# МЕНЮ САЙТА (nav.py)
# ===========================================================================
# Блок `nav = [...]` в zensical.toml между маркерами NAV_BEGIN и NAV_END целиком формирует nav.py. Неизменная часть меню
# задаётся списком NAV ниже (продукт задаёт свой в rms.toml), а вместо элемента REGISTRY скрипт подставляет группу
# реестра, собранную по папкам REGISTRY_DIR, вместо GLOBAL_SF — группу глобальных функциональностей из папок
# GLOBAL_SF_DIR. Пути страниц — относительно docs/. Страницы, которых нет на диске, пропускаются (с предупреждением).

NAV_BEGIN = "# BEGIN GENERATED NAV — не редактируйте вручную"
NAV_BEGIN_PREFIX = "# BEGIN GENERATED NAV"
NAV_END = "# END GENERATED NAV"
# Начальный маркер ищется по началу строки (после него допустим любой комментарий), конечный — как есть
NAV_RE = re.compile(re.escape(NAV_BEGIN_PREFIX) + r"[^\n]*\n.*?" + re.escape(NAV_END), re.DOTALL)

# Место группы реестра в NAV
REGISTRY = "<REGISTRY>"
# Место группы глобальных функциональностей в NAV
GLOBAL_SF = "<GLOBAL_SF>"

# Неизменная часть меню. Элемент: ("Название", "путь.md") — страница; ("Название", [элементы]) — группа;
# "путь.md" без названия — индекс группы (первым элементом группы: щелчок на группе открывает эту страницу).
# Здесь — меню по умолчанию; продукт задаёт своё в rms.toml ([nav] items), где место групп обозначают строки "@registry"
# и "@global_sf".
NAV = [
    ("О продукте", "index.md"),
    ("Требования", [GLOBAL_SF, REGISTRY]),
]

# --- Группа реестра ---
# Папка реестра: каждая её подпапка с index.md — фича. Индекс самой папки открывается щелчком на группе.
REGISTRY_TITLE = "Реестр требований"
REGISTRY_DIR = "requirements/features"

# Название фичи — текст после ID в заголовке требования F в index.md фичи: «## F-PT. Справочник видов изделий {#f-pt}»
# → «Справочник видов изделий». Нет такого заголовка — заголовок первого уровня без якоря (с предупреждением), нет и
# его — имя папки.
FEATURE_TITLE_RE = re.compile(
    r"^#{1,6}[ \t]+F-[A-Z0-9]+(?:-[A-Z0-9]+)*\.[ \t]+(?P<title>.+?)(?:[ \t]*\{[^}\n]*\})?[ \t]*$", re.MULTILINE)
H1_RE = re.compile(r"^#[ \t]+(?P<title>.+?)(?:[ \t]*\{[^}]*\})?[ \t]*$", re.MULTILINE)

# Порядок фич: поле `order` в метаданных index.md фичи (меньше — выше), без него — после, по имени папки
ORDER_KEY = "order"

# Подпапки фичи: имя папки → название в меню. Порядок в словаре — порядок в меню; папки не из словаря идут после,
# по алфавиту, с именем папки вместо названия (и предупреждением).
FOLDER_TITLES = {
    "f": "Общие",
    "sf-list": "Список",
    "sf-read": "Карточка",
    "sf-create": "Создание",
    "sf-update": "Изменение",
    "sf-activation": "Активация",
    "sf-delete": "Удаление",
}

# Файлы внутри фичи и её подпапок (кроме index.md): имя файла → название в меню. Порядок в словаре — порядок в меню;
# файлы не из словаря идут после, по алфавиту, с именем файла вместо названия (и предупреждением).
FILE_TITLES = {
    "uc.md": "UC",
    "dr.md": "DR",
    "fr.md": "FR",
    "ar.md": "AR",
    "nfr.md": "NFR",
    "ui.md": "UI",
}
# Приставка к названию файла, лежащего прямо в папке фичи (общие требования фичи): «Общие UC», «Общие DR»…
FEATURE_FILE_PREFIX = "Общие "

# --- Группа глобальных функциональностей ---
# Подпапки GLOBAL_SF_DIR с приставкой GLOBAL_SF_PREFIX и файлом index.md — глобальные функциональности. Внутри — как
# у подфункциональности реестра: index.md, затем файлы по FILE_TITLES («DR», «FR», «UI»…).
GLOBAL_SF_TITLE = "Глобальные функциональности"
GLOBAL_SF_DIR = "requirements/global"
GLOBAL_SF_PREFIX = "sf-g-"
# Папка → название в меню. Порядок в словаре — порядок в меню; папки не из словаря идут после, по алфавиту, с именем
# папки вместо названия (и предупреждением).
GLOBAL_SF_TITLES: dict[str, str] = {}             # у каждого продукта свои: [global_sf.titles] в rms.toml


# ===========================================================================
# СТАТУСЫ И ЗНАЧКИ (status.py)
# ===========================================================================
# Статус SF аналитик вписывает вручную в index.md папки sf-*: строка «- **Статус**: анализ» (первая такая строка в файле).
# По нему скрипт ведёт метаданные этого index.md: `status` (русское название статуса — его выводит «паспорт» страницы,
# custom/passport.html) и `icon` (значок в левом меню). Статус F вычисляется из статусов её SF по правилу Jira для
# эпиков (см. status.py); `status` и `icon` в метаданных вручную не правят.

# Статус → значок (форма как в тексте Markdown; в поле `icon` скрипт пишет её как lucide/<имя>)
STATUS_ICONS = {
    "бэклог": ":lucide-file:",
    "анализ": ":lucide-file-pen-line:",
    "готово к разработке": ":lucide-file-check:",
    "разработка": ":lucide-file-braces:",
    "реализовано": ":lucide-file-text:",
    "архив": ":lucide-file-archive:",
    "в работе": ":lucide-file-clock:",         # только для F (вычисляется, вручную не вписывают)
}
# Статусы, которые аналитик может вписать в SF вручную
SF_STATUSES = ["бэклог", "анализ", "готово к разработке", "разработка", "реализовано", "архив"]

# Статус F по правилу Jira для эпиков (SF в архиве не учитываются):
#   все SF в бэклоге — F в бэклоге; все SF реализованы — F реализована; иначе — F в работе; все SF в архиве — F в архиве.
BACKLOG_STATUS = "бэклог"
DONE_STATUS = "реализовано"
IN_PROGRESS_STATUS = "в работе"
ARCHIVED_STATUS = "архив"

SF_FOLDER_PREFIX = "sf-"                # папки подфункциональностей внутри папки фичи
STATUS_KEY = "status"
ICON_KEY = "icon"
STATUS_LINE_RE = re.compile(r"^[-*][ \t]+\*\*Статус\*\*:[ \t]*(?P<status>.*?)[ \t]*$", re.MULTILINE)

# --- Приоритет (тот же скрипт status.py) ---
# Приоритет SF аналитик вписывает вручную в index.md папки sf-*: строка «- **Приоритет**: must». Скрипт записывает его
# в поле `priority` метаданных (первой строкой). Приоритет F вычисляется: самый строгий приоритет среди её SF (SF в архиве
# не учитываются, если есть другие). В тексте F строку «Приоритет» не ведут.
PRIORITY_KEY = "priority"
PRIORITY_ORDER = ["must", "should", "could", "won't"]   # от самого строгого к самому мягкому (MoSCoW)
PRIORITY_LINE_RE = re.compile(r"^[-*][ \t]+\*\*Приоритет\*\*:[ \t]*(?P<priority>.*?)[ \t]*$", re.MULTILINE)


# ===========================================================================
# ДАШБОРД РЕЕСТРА (dashboard.py)
# ===========================================================================
# Дашборд записывается в DASHBOARD_PAGE между маркерами DASHBOARD_BEGIN и DASHBOARD_END (если маркеров нет — сразу
# после заголовка первого уровня). Всё, что вне маркеров, ведут вручную. Оформление — custom/css/extra.css, раздел 12.

DASHBOARD_PAGE = "requirements/features/index.md"     # относительно docs/
DASHBOARD_BEGIN = "<!-- BEGIN GENERATED DASHBOARD — не редактируйте вручную -->"
DASHBOARD_BEGIN_PREFIX = "<!-- BEGIN GENERATED DASHBOARD"
DASHBOARD_END = "<!-- END GENERATED DASHBOARD -->"
DASHBOARD_RE = re.compile(re.escape(DASHBOARD_BEGIN_PREFIX) + r"[^\n]*\n.*?" + re.escape(DASHBOARD_END), re.DOTALL)

# Статусы на плитках F (что может получить фича) и класс оформления каждого статуса (custom/css/extra.css)
F_STATUSES = ["бэклог", "в работе", "реализовано", "архив"]
STATUS_CSS = {
    "бэклог": "backlog",
    "анализ": "analysis",
    "готово к разработке": "ready",
    "разработка": "development",
    "реализовано": "released",
    "архив": "archived",
    "в работе": "in-progress",
}
# Пояснения в блоке «Статусы функциональностей»
STATUS_DESCRIPTIONS = {
    "бэклог": "зафиксированное сырое требование или идея",
    "анализ": "детализация и согласование требования",
    "готово к разработке": "утверждённое требование, готовое к реализации",
    "разработка": "требование в работе у команды разработки и тестирования",
    "реализовано": "код, связанный с требованием, успешно развёрнут на проде",
    "архив": "отклонённое или устаревшее требование",
    "в работе": "только у F: часть её SF уже в работе, но реализованы ещё не все",
}
TOTAL_ICON = ":lucide-files:"

# Проверки блока «Требует внимания»
FR_FILE = "fr.md"                                    # функциональные требования SF
FR_HEADING_RE = re.compile(r"^#{2,3}[ \t]+(?P<id>FR-[A-Z0-9]+(?:-[A-Z0-9]+)*)\b", re.MULTILINE)
ACCEPTANCE_MARK = "```gherkin"                       # критерии приёмки внутри блока FR
# ID требования в начале заголовка; после ID — точка и название («## FR-PT-CREATE-001. Создание записи…»), якорь или
# конец строки
REQUIREMENT_ID_RE = re.compile(
    r"^#{1,3}[ \t]+(?P<id>(?:F|SF|FR|DR|AR|UC|NFR|UI)-[A-Z0-9]+(?:-[A-Z0-9]+)*)(?=[.: \t{]|$)", re.MULTILINE)
ASSUMPTION_RE = re.compile(r"^[-*][ \t]+\*\*(?P<id>[A-Z0-9]+(?:-[A-Z0-9]+)*\.H\d+)\*\*[ \t]*\n(?P<body>(?:[ \t]+\S.*\n?)*)",
                           re.MULTILINE)
ASSUMPTION_STATUS_RE = re.compile(r"\*\*Статус\*\*:[ \t]*(?P<value>.*?)[ \t]*$", re.MULTILINE)
ASSUMPTION_OWNER_RE = re.compile(r"\*\*Подтверждает\*\*:[ \t]*(?P<value>.*?)[ \t]*$", re.MULTILINE)
ASSUMPTION_ACCEPTED = "принято"
ANCHOR_RE = re.compile(r"\{#(?P<id>[\w-]+)|\bid=[\"'](?P<html>[\w-]+)[\"']")
REF_LINK_RE = re.compile(r"^\[(?P<label>[^\]]+)\]:[ \t]*<?(?P<url>[^>\s]+)>?", re.MULTILINE)
INLINE_LINK_RE = re.compile(r"\]\((?P<url>[^)\s]+)\)")
ATTENTION_LIST_LIMIT = 10                            # сколько строк показывать в группе, остальное — «…ещё N»

# «Последние изменения»: сколько записей журналов показывать
CHANGES_LIMIT = 5
JOURNAL_ENTRY_RE = re.compile(
    r"^- \[Версия (?P<version>[\d.]+) \((?P<when>\d\d\.\d\d\.\d{4} \d\d:\d\d(?::\d\d)?)(?:; (?P<files>[^)]*))?\)\]"
    r"\((?P<url>[^)]+)\)(?:\{[^}]*\})?\. [^:\n]+:[ \t]*(?P<author>.+?)[ \t]*$", re.MULTILINE)


# ===========================================================================
# НАСТРОЙКИ ПРОДУКТА (rms.toml в корне репозитория продукта)
# ===========================================================================
# Всё, что выше, — значения по умолчанию. Продукт может переопределить в rms.toml (все разделы необязательны):
#
#   [nav]
#   items = [ { "О продукте" = "index.md" }, { "Требования" = [ "@global_sf", "@registry" ] } ]
#                                      — неизменная часть меню (как блок nav в zensical.toml); "@registry" и "@global_sf"
#                                        — места групп реестра и глобальных функциональностей
#   [registry]   title, dir            — REGISTRY_TITLE, REGISTRY_DIR
#   [dashboard]  page                  — DASHBOARD_PAGE
#   [global_sf]  title, dir, prefix    — GLOBAL_SF_TITLE, GLOBAL_SF_DIR, GLOBAL_SF_PREFIX
#   [global_sf.titles]                 — GLOBAL_SF_TITLES (папка = "название"; заменяет словарь целиком)
#   [titles]     feature_file_prefix   — FEATURE_FILE_PREFIX
#   [titles.folders], [titles.files]   — дополняют FOLDER_TITLES и FILE_TITLES: та же папка (файл) — новое название,
#                                        новые — в конец словаря (порядок в меню)

PRODUCT_NAV_MARKERS = {"@registry": REGISTRY, "@global_sf": GLOBAL_SF}


class ProductSettingsError(ValueError):
    """Ошибка в rms.toml: скрипты сообщают о ней и завершаются с кодом 1."""


def _nav_items(items: list, where: str) -> list:
    """Меню из rms.toml (как nav в zensical.toml) → формат NAV."""
    result = []
    for item in items:
        if isinstance(item, str):
            result.append(PRODUCT_NAV_MARKERS.get(item, item))
        elif isinstance(item, dict) and len(item) == 1:
            title, value = next(iter(item.items()))
            if isinstance(value, list):
                result.append((title, _nav_items(value, f"{where} → {title}")))
            elif isinstance(value, str):
                result.append((title, value))
            else:
                raise ProductSettingsError(f"rms.toml [nav] {where}: у пункта «{title}» значение не строка и не список")
        else:
            raise ProductSettingsError(f"rms.toml [nav] {where}: пункт должен быть строкой или {{ \"Название\" = … }}")
    return result


def _load_product_settings(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ProductSettingsError(f"rms.toml: некорректный TOML ({exc})") from exc


try:
    _product = _load_product_settings(PRODUCT_SETTINGS)
    if "nav" in _product:
        NAV = _nav_items(_product["nav"].get("items", []), "items")
except ProductSettingsError as _exc:
    raise SystemExit(f"ОШИБКА: {_exc}") from None     # сообщение в stderr, код возврата 1
REGISTRY_TITLE = _product.get("registry", {}).get("title", REGISTRY_TITLE)
REGISTRY_DIR = _product.get("registry", {}).get("dir", REGISTRY_DIR)
DASHBOARD_PAGE = _product.get("dashboard", {}).get("page", DASHBOARD_PAGE)
GLOBAL_SF_TITLE = _product.get("global_sf", {}).get("title", GLOBAL_SF_TITLE)
GLOBAL_SF_DIR = _product.get("global_sf", {}).get("dir", GLOBAL_SF_DIR)
GLOBAL_SF_PREFIX = _product.get("global_sf", {}).get("prefix", GLOBAL_SF_PREFIX)
GLOBAL_SF_TITLES = dict(_product.get("global_sf", {}).get("titles", GLOBAL_SF_TITLES))
FEATURE_FILE_PREFIX = _product.get("titles", {}).get("feature_file_prefix", FEATURE_FILE_PREFIX)
FOLDER_TITLES = {**FOLDER_TITLES, **_product.get("titles", {}).get("folders", {})}
FILE_TITLES = {**FILE_TITLES, **_product.get("titles", {}).get("files", {})}
