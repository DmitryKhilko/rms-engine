/* ==========================================================================
   passport.js — «паспорт» страницы под заголовком первого уровня

   Встраивается в каждую страницу из custom/main.html (блок scripts) ДО sections.js.
   Шаблон custom/passport.html выводит блок dl.page-passport (данные из Front Matter) перед
   текстом страницы. Если текст начинается с заголовка первого уровня, скрипт переносит блок
   сразу под него: вверху — название страницы, под ним — паспорт. Если первым идёт другой
   элемент (например, раздел «Журнал изменений»), блок остаётся вверху страницы.
   Без JavaScript блок тоже остаётся вверху (всё читается).

   Между паспортом и заголовком могут стоять служебные элементы темы (кнопка «Править
   страницу») и полоса «Свернуть всё / Развернуть всё» из sections.js — они пропускаются.

   Запускается событием темы document$ — после загрузки страницы и после каждой мгновенной
   навигации; повторный вызов безопасен.

   Файл встраивается как шаблон Jinja, поэтому в нём (и в комментариях) нельзя писать:
   две открывающие фигурные скобки подряд, фигурную скобку с процентом, фигурную скобку
   с решёткой и закрывающий тег script.
   ========================================================================== */

(function () {
  "use strict";

  var SELECTORS = {
    article: "article.md-content__inner",               /* текст страницы */
    passport: "dl.page-passport",                       /* блок паспорта */
    skip: ".md-content__button, .section-toolbar"       /* элементы, которые пропускаются по пути к h1 */
  };

  function place() {
    var article = document.querySelector(SELECTORS.article);
    if (!article) return;
    var passport = article.querySelector(":scope > " + SELECTORS.passport);
    if (!passport) return;
    var node = passport.nextElementSibling;
    while (node && node.matches(SELECTORS.skip)) {
      node = node.nextElementSibling;
    }
    if (node && node.tagName === "H1") {
      node.insertAdjacentElement("afterend", passport);
    }
  }

  if (typeof document$ !== "undefined" && document$ && typeof document$.subscribe === "function") {
    document$.subscribe(place);
  } else if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", place);
  } else {
    place();
  }
})();
