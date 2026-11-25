/* ==========================================================================
   sections.js — сворачивание разделов страницы

   Встраивается в каждую страницу из custom/main.html (блок scripts).
   Оформление кнопок — в custom/css/extra.css (разделы 9 и 10).

   Что делает:
   1. Ставит стрелку в заголовки h2–h6: щелчок сворачивает раздел (всё до следующего
      заголовка того же или более высокого уровня). Заголовок h1 не сворачивается.
   2. Показывает над h1 полосу «Свернуть всё / Развернуть всё»; она остаётся под шапкой
      сайта при прокрутке.
   3. Сворачивает при открытии страницы заголовки с классом collapsed, который автор
      записывает в документе: ## Журнал изменений { #change-history .collapsed }
   4. Повторяет состояние разделов в правом меню «Содержание»: у свёрнутого раздела
      подпункты скрыты, а у пунктов с подпунктами есть своя стрелка.
   5. Режим «аккордеон» (ACCORDION): при ручном разворачивании раздела соседние разделы
      того же уровня сворачиваются.
   6. Раскрывает нужные разделы при переходе по ссылке или адресу с якорем.

   Состояние между визитами не хранится: после загрузки все разделы развёрнуты,
   кроме помеченных collapsed.

   Файл встраивается как шаблон Jinja, поэтому в нём (и в комментариях) нельзя писать:
   две открывающие фигурные скобки подряд, фигурную скобку с процентом, фигурную скобку
   с решёткой и закрывающий тег script.
   ========================================================================== */

(function () {
  "use strict";

  /* Тема может выполнить встроенный скрипт повторно при переходе на другую страницу.
     Без этой проверки обработчики событий удваивались бы при каждом переходе. */
  if (window.__sectionsLoaded) {
    return;
  }
  window.__sectionsLoaded = true;


  /* ------------------------------------------------------------------------
     НАСТРОЙКИ
     ------------------------------------------------------------------------ */

  /* true: при ручном разворачивании раздела соседние разделы того же уровня сворачиваются */
  var ACCORDION = true;

  /* Зазор в пикселях между полосой кнопок и заголовком, к которому ведёт ссылка */
  var SCROLL_GAP = 8;

  /* Все селекторы элементов темы: если Zensical изменит разметку, править только здесь */
  var SELECTORS = {
    article: "article.md-content__inner",      /* текст страницы */
    toc: ".md-sidebar--secondary",             /* правое меню «Содержание» */
    tocLink: "a.md-nav__link[href*='#']",      /* ссылки на заголовки в правом меню */
    tocNested: ".md-nav",                      /* вложенный список подпунктов внутри пункта меню */
    header: "header.md-header",                /* шапка сайта */
    tabs: ".md-tabs",                          /* вкладки под шапкой */
    service: ".md-source-file, .footnote",     /* служебные блоки в конце статьи, не входят в разделы */
    hashLink: "a[href*='#']"                   /* любая ссылка с якорем */
  };

  /* Классы, которые скрипт добавляет в разметку (используются в extra.css) */
  var CLS = {
    toolbar: "section-toolbar",         /* полоса «Свернуть всё / Развернуть всё» */
    heading: "section-heading",         /* заголовок, у которого есть содержимое и стрелка */
    toggle: "section-toggle",           /* стрелка в заголовке */
    body: "section-body",               /* контейнер с содержимым раздела */
    isCollapsed: "is-collapsed",        /* раздел свёрнут сейчас (ставит скрипт) */
    startCollapsed: "collapsed",        /* раздел свёрнут при открытии (ставит автор документа) */
    tocCollapsible: "toc-collapsible",  /* пункт меню со стрелкой: у него есть подпункты */
    tocToggle: "toc-toggle",            /* стрелка в пункте меню */
    tocCollapsed: "toc-collapsed"       /* пункт меню с отключёнными подпунктами */
  };

  var TEXT = {
    collapseAll: "Свернуть всё",
    expandAll: "Развернуть всё",
    collapseAllHint: "Свернуть все разделы страницы",
    expandAllHint: "Развернуть все разделы страницы",
    toolbarLabel: "Управление разделами страницы",
    collapseSection: "Свернуть раздел",
    expandSection: "Развернуть раздел"
  };


  /* ------------------------------------------------------------------------
     ОБЩИЕ ФУНКЦИИ
     ------------------------------------------------------------------------ */

  function getArticle() {
    return document.querySelector(SELECTORS.article);
  }

  function isHeading(node) {
    return !!node && node.nodeType === 1 && /^H[1-6]$/.test(node.tagName);
  }

  /* Уровень заголовка: для h3 вернёт 3 */
  function levelOf(heading) {
    return parseInt(heading.tagName.charAt(1), 10);
  }

  /* Идентификатор из адреса: "#fr-001" даёт "fr-001"; при ошибке записи вернёт пустую строку */
  function idFromHash(hash) {
    try {
      return decodeURIComponent(hash.replace(/^#/, ""));
    } catch (error) {
      return "";
    }
  }

  /* Все заголовки текущей страницы, которые умеют сворачиваться */
  function getSectionHeadings(article) {
    return Array.prototype.slice.call(article.querySelectorAll("." + CLS.heading));
  }


  /* ------------------------------------------------------------------------
     ПРАВОЕ МЕНЮ «СОДЕРЖАНИЕ»
     Пункт меню связывается с заголовком по якорю в ссылке.
     ------------------------------------------------------------------------ */

  /* Соответствие «идентификатор заголовка → элемент li пункта меню».
     Если меню на странице нет (узкий экран), остаётся пустым. */
  var tocItems = {};

  /* Строит соответствие по текущему меню. Тема записывает ссылки полным адресом
     (https://сайт/страница/#id), поэтому якорь берём из свойства hash, а не из href. */
  function buildTocMap() {
    var map = {};
    var toc = document.querySelector(SELECTORS.toc);
    if (!toc) {
      return map;
    }
    Array.prototype.forEach.call(toc.querySelectorAll(SELECTORS.tocLink), function (link) {
      var id = idFromHash(link.hash);
      if (id) {
        map[id] = link.closest("li");
      }
    });
    return map;
  }

  /* Добавляет пункту меню стрелку (один раз). Стрелка лежит рядом со ссылкой, а не внутри
     неё: кнопка внутри ссылки недопустима, и щелчок по ней вёл бы к заголовку. */
  function ensureTocToggle(item, heading) {
    var button = item.querySelector(":scope > ." + CLS.tocToggle);
    if (button) {
      return button;
    }
    button = document.createElement("button");
    button.type = "button";
    button.className = CLS.tocToggle;
    button.addEventListener("click", function (event) {
      event.preventDefault();
      event.stopPropagation();
      toggleSection(heading);
    });
    var link = item.querySelector(":scope > a");
    item.insertBefore(button, link ? link.nextSibling : null);
    return button;
  }

  /* Показывает в меню состояние раздела: подпункты скрыты (collapsed) или видны */
  function syncToc(heading, collapsed) {
    var item = tocItems[heading.id];
    if (item && !item.isConnected) {
      /* Тема перестроила меню после подготовки страницы: ищем пункт заново */
      tocItems = buildTocMap();
      item = tocItems[heading.id];
    }
    if (!item) {
      return;
    }
    if (item.querySelector(":scope > " + SELECTORS.tocNested)) {
      item.classList.add(CLS.tocCollapsible);
      var toggle = ensureTocToggle(item, heading);
      toggle.setAttribute("aria-expanded", String(!collapsed));
      toggle.setAttribute("aria-label", sectionLabel(heading, collapsed));
    }
    item.classList.toggle(CLS.tocCollapsed, collapsed);
  }


  /* ------------------------------------------------------------------------
     СОСТОЯНИЕ РАЗДЕЛОВ
     ------------------------------------------------------------------------ */

  /* Подпись стрелки для программ чтения с экрана: действие и название раздела */
  function sectionLabel(heading, collapsed) {
    return (collapsed ? TEXT.expandSection : TEXT.collapseSection) + ": " + heading.sectionTitle;
  }

  /* Сворачивает или разворачивает раздел и приводит в соответствие стрелки,
     подписи и правое меню. until-found прячет содержимое, но оставляет его доступным
     поиску по странице (Ctrl+F): при совпадении браузер раскроет раздел сам. */
  function setSection(heading, collapsed) {
    var body = heading.sectionBody;
    if (!body) {
      return;
    }
    if (collapsed) {
      body.setAttribute("hidden", "until-found");
    } else {
      body.removeAttribute("hidden");
    }
    heading.classList.toggle(CLS.isCollapsed, collapsed);
    heading.sectionToggle.setAttribute("aria-expanded", String(!collapsed));
    heading.sectionToggle.setAttribute("aria-label", sectionLabel(heading, collapsed));
    syncToc(heading, collapsed);
  }

  /* Сворачивает соседей раздела (заголовки того же уровня с тем же родителем) */
  function collapseSiblings(heading) {
    if (!ACCORDION || !heading.parentElement) {
      return;
    }
    var level = levelOf(heading);
    Array.prototype.forEach.call(heading.parentElement.children, function (node) {
      if (node !== heading && isHeading(node) && levelOf(node) === level && node.sectionBody) {
        setSection(node, true);
      }
    });
  }

  /* Переключение раздела читателем (стрелка в заголовке или в меню).
     Разворачивание запускает «аккордеон». */
  function toggleSection(heading) {
    var collapse = !heading.classList.contains(CLS.isCollapsed);
    setSection(heading, collapse);
    if (!collapse) {
      collapseSiblings(heading);
    }
  }

  /* Раскрывает свёрнутые разделы, скрывающие element, и сам element, если это свёрнутый
     заголовок. accordion = true запускает режим «аккордеон» для раскрытых разделов.
     Возвращает true, если что-то раскрыто. */
  function revealTarget(element, article, accordion) {
    var changed = false;
    for (var node = element; node && node !== article; node = node.parentElement) {
      var heading = null;
      if (node === element && node.classList.contains(CLS.isCollapsed)) {
        heading = node;
      } else if (node.classList.contains(CLS.body) && node.hasAttribute("hidden")) {
        heading = node.sectionHeading;
      }
      if (heading) {
        setSection(heading, false);
        if (accordion) {
          collapseSiblings(heading);
        }
        changed = true;
      }
    }
    return changed;
  }

  function collapseAll(article) {
    getSectionHeadings(article).forEach(function (heading) {
      setSection(heading, true);
    });
    /* Страница стала короче: возвращаем читателя к заголовку, чтобы он не оказался в пустоте */
    var title = article.querySelector("h1");
    if (title) {
      title.scrollIntoView({ block: "start" });
    }
  }

  function expandAll(article) {
    getSectionHeadings(article).forEach(function (heading) {
      setSection(heading, false);
    });
  }


  /* ------------------------------------------------------------------------
     ПОСТРОЕНИЕ РАЗДЕЛОВ
     ------------------------------------------------------------------------ */

  /* Делает заголовок сворачиваемым: переносит содержимое раздела в контейнер
     и добавляет стрелку. Если под заголовком ничего нет, пропускает его.
     index нужен для уникального id контейнера. */
  function buildSection(heading, index) {
    var level = levelOf(heading);
    var nodes = [];
    var node = heading.nextElementSibling;

    /* Раздел идёт до заголовка того же или более высокого уровня или до служебных
       блоков в конце статьи. Контейнеры вложенных разделов уже созданы (см. buildSections)
       и попадают внутрь как обычные блоки. */
    while (node && !(isHeading(node) && levelOf(node) <= level) && !node.matches(SELECTORS.service)) {
      nodes.push(node);
      node = node.nextElementSibling;
    }
    if (nodes.length === 0) {
      return;
    }

    var body = document.createElement("div");
    body.className = CLS.body;
    body.id = CLS.body + "-" + index;
    heading.parentNode.insertBefore(body, heading.nextSibling);
    nodes.forEach(function (child) {
      body.appendChild(child);
    });

    var button = document.createElement("button");
    button.type = "button";
    button.className = CLS.toggle;
    button.setAttribute("aria-controls", body.id);
    button.addEventListener("click", function () {
      toggleSection(heading);
    });
    heading.insertBefore(button, heading.firstChild);
    heading.classList.add(CLS.heading);

    /* Связи между заголовком, контейнером и стрелкой нужны остальным функциям.
       Название берём до вставки стрелки, чтобы оно не содержало лишнего. */
    heading.sectionBody = body;
    heading.sectionToggle = button;
    heading.sectionTitle = heading.textContent.replace(/\s+/g, " ").trim();
    body.sectionHeading = heading;

    setSection(heading, heading.classList.contains(CLS.startCollapsed));

    /* Поиск по странице нашёл текст в скрытом разделе: приводим в порядок стрелки
       этого раздела и внешних разделов (браузер раскрывает контейнер сам) */
    body.addEventListener("beforematch", function () {
      revealTarget(body, getArticle(), false);
      setSection(heading, false);
    });
  }

  /* Обходит заголовки h2–h6, лежащие прямо в статье, с конца страницы к началу:
     так при построении раздела верхнего уровня вложенные уже готовы. */
  function buildSections(article) {
    var headings = Array.prototype.slice.call(article.querySelectorAll("h2, h3, h4, h5, h6"))
      .filter(function (heading) {
        return heading.parentElement === article;
      });
    for (var i = headings.length - 1; i >= 0; i--) {
      buildSection(headings[i], i);
    }
  }


  /* ------------------------------------------------------------------------
     ПОЛОСА «СВЕРНУТЬ ВСЁ / РАЗВЕРНУТЬ ВСЁ»
     ------------------------------------------------------------------------ */

  function makeToolbarButton(label, hint, action) {
    var button = document.createElement("button");
    button.type = "button";
    button.textContent = label;
    button.title = hint;
    button.addEventListener("click", action);
    return button;
  }

  /* Ставит полосу перед заголовком h1 (если его нет — в начало статьи) */
  function buildToolbar(article) {
    var bar = document.createElement("div");
    bar.className = CLS.toolbar;
    bar.setAttribute("role", "toolbar");
    bar.setAttribute("aria-label", TEXT.toolbarLabel);
    bar.appendChild(makeToolbarButton(TEXT.collapseAll, TEXT.collapseAllHint, function () {
      collapseAll(article);
    }));
    bar.appendChild(makeToolbarButton(TEXT.expandAll, TEXT.expandAllHint, function () {
      expandAll(article);
    }));

    var title = article.querySelector("h1");
    article.insertBefore(bar, title && title.parentElement === article ? title : article.firstChild);
  }

  /* Измеряет шапку и вкладки и передаёт стилям:
       --section-toolbar-top    — на каком расстоянии от верха экрана «прилипает» полоса;
       --section-scroll-offset  — отступ над заголовком при переходе по ссылке,
                                  чтобы шапка и полоса его не закрывали. */
  function updateOffsets() {
    var top = 0;
    [SELECTORS.header, SELECTORS.tabs].forEach(function (selector) {
      var element = document.querySelector(selector);
      if (element) {
        var rect = element.getBoundingClientRect();
        if (rect.height > 0) {
          top = Math.max(top, rect.bottom);
        }
      }
    });
    top = Math.ceil(top);

    var bar = document.querySelector("." + CLS.toolbar);
    var root = document.documentElement;
    root.style.setProperty("--section-toolbar-top", top + "px");
    root.style.setProperty("--section-scroll-offset", (top + (bar ? bar.offsetHeight : 0) + SCROLL_GAP) + "px");
  }


  /* ------------------------------------------------------------------------
     ССЫЛКИ, АДРЕС И ПЕЧАТЬ
     ------------------------------------------------------------------------ */

  /* Раскрывает разделы, скрывающие место, на которое указывает адрес страницы */
  function revealHash() {
    var article = getArticle();
    var id = idFromHash(location.hash);
    var target = article && id ? document.getElementById(id) : null;
    if (target && article.contains(target) && revealTarget(target, article, false)) {
      /* Раздел раскрылся после того, как браузер прокрутил страницу: прокручиваем заново */
      target.scrollIntoView();
    }
  }

  /* Свёрнутое содержимое на бумагу не попадает: перед печатью раскрываем всё,
     после печати возвращаем прежнее состояние */
  var collapsedBeforePrint = [];

  function beforePrint() {
    var article = getArticle();
    if (!article) {
      return;
    }
    collapsedBeforePrint = getSectionHeadings(article).filter(function (heading) {
      return heading.classList.contains(CLS.isCollapsed);
    });
    expandAll(article);
  }

  function afterPrint() {
    collapsedBeforePrint.forEach(function (heading) {
      setSection(heading, true);
    });
    collapsedBeforePrint = [];
  }

  /* Щелчок по ссылке на место этой же страницы раскрывает скрывающие его разделы
     раньше, чем браузер выполнит переход (фаза перехвата). «Аккордеон» включается
     только для ссылок правого меню: ссылки в тексте соседей не сворачивают. */
  function onLinkClick(event) {
    var link = event.target.closest ? event.target.closest(SELECTORS.hashLink) : null;
    var article = getArticle();
    if (!link || !article || link.host !== location.host || link.pathname !== location.pathname) {
      return;
    }
    var id = idFromHash(link.hash);
    var target = id ? document.getElementById(id) : null;
    if (target && article.contains(target)) {
      revealTarget(target, article, !!link.closest(SELECTORS.toc));
    }
  }

  /* Обработчики окна и документа подключаются один раз: при переходах по сайту
     страница не перезагружается */
  var globalHandlersBound = false;

  function bindGlobalHandlers() {
    if (globalHandlersBound) {
      return;
    }
    globalHandlersBound = true;
    document.addEventListener("click", onLinkClick, true);
    window.addEventListener("hashchange", revealHash);
    window.addEventListener("resize", updateOffsets);
    window.addEventListener("load", updateOffsets);
    window.addEventListener("beforeprint", beforePrint);
    window.addEventListener("afterprint", afterPrint);
    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(updateOffsets);   /* загрузка шрифтов может сдвинуть шапку */
    }
  }


  /* ------------------------------------------------------------------------
     ЗАПУСК
     ------------------------------------------------------------------------ */

  /* Подготавливает текущую страницу. Вызывается при загрузке и при каждом переходе
     на другую страницу (мгновенная навигация подменяет содержимое без перезагрузки). */
  function init() {
    var article = getArticle();
    if (!article || article.getAttribute("data-sections-ready")) {
      return;   /* статьи нет или страница уже подготовлена */
    }
    article.setAttribute("data-sections-ready", "true");

    tocItems = buildTocMap();   /* меню нужно до построения разделов: collapsed сворачивает и его */
    buildSections(article);
    if (getSectionHeadings(article).length > 0) {
      buildToolbar(article);
    }

    bindGlobalHandlers();
    updateOffsets();
    revealHash();
  }

  /* document$ — поток событий темы: срабатывает после загрузки каждой страницы,
     в том числе при мгновенной навигации. Без него запускаем один раз после загрузки. */
  if (typeof document$ !== "undefined" && document$ && typeof document$.subscribe === "function") {
    document$.subscribe(init);
  } else if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
