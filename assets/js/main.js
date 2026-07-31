(function () {
  "use strict";

  function initNavigation() {
    var sidebar = document.getElementById("sidebar");
    var brandLink = document.querySelector(".sidebar-brand");
    var brandTitle = document.querySelector(".sidebar-brand .brand-title");
    var activeSectionLink = document.querySelector(
      '.nav-sections a[aria-current="page"]',
    );

    function showCurrentSection(link) {
      if (!link || !brandTitle) {
        return;
      }
      var sectionTitle = link.textContent.trim();
      brandTitle.textContent = sectionTitle;
      if (brandLink) {
        brandLink.setAttribute("title", "返回手册首页");
        brandLink.setAttribute(
          "aria-label",
          "返回手册首页，当前小节：" + sectionTitle,
        );
      }
    }

    showCurrentSection(activeSectionLink);

    document.querySelectorAll(".nav-chapter").forEach(function (chapter) {
      if (chapter.querySelector('[aria-current="page"]')) {
        chapter.open = true;
      } else if (document.body.dataset.pageType === "chapter") {
        chapter.open = false;
      }
    });

    var menuButton = document.getElementById("menu-toggle");
    var drawerOverlay = document.getElementById("drawer-overlay");
    var collapseButton = null;

    function readCollapsedPreference() {
      try {
        return localStorage.getItem("manual-sidebar-collapsed") === "true";
      } catch (error) {
        return false;
      }
    }

    function saveCollapsedPreference(collapsed) {
      try {
        localStorage.setItem(
          "manual-sidebar-collapsed",
          collapsed ? "true" : "false",
        );
      } catch (error) {
        // Local files can disable storage in some browsers; folding still works.
      }
    }

    function setSidebarCollapsed(collapsed, savePreference) {
      document.body.classList.toggle("sidebar-collapsed", collapsed);
      if (collapseButton) {
        collapseButton.setAttribute("aria-expanded", String(!collapsed));
        collapseButton.setAttribute(
          "aria-label",
          collapsed ? "展开章节导航" : "折叠章节导航",
        );
        collapseButton.setAttribute(
          "title",
          collapsed ? "展开章节导航" : "折叠章节导航",
        );
        collapseButton.textContent = collapsed ? "›" : "‹";
      }
      if (savePreference) {
        saveCollapsedPreference(collapsed);
      }
    }

    if (sidebar) {
      collapseButton = document.createElement("button");
      collapseButton.className = "sidebar-collapse-toggle";
      collapseButton.type = "button";
      collapseButton.setAttribute("aria-controls", "sidebar");
      sidebar.insertAdjacentElement("afterend", collapseButton);
      setSidebarCollapsed(readCollapsedPreference(), false);
      collapseButton.addEventListener("click", function () {
        setSidebarCollapsed(
          !document.body.classList.contains("sidebar-collapsed"),
          true,
        );
      });
    }

    function setDrawer(open) {
      document.body.classList.toggle("sidebar-open", open);
      if (menuButton) {
        menuButton.setAttribute("aria-expanded", String(open));
      }
    }

    if (menuButton) {
      menuButton.addEventListener("click", function () {
        setDrawer(!document.body.classList.contains("sidebar-open"));
      });
    }
    if (drawerOverlay) {
      drawerOverlay.addEventListener("click", function () {
        setDrawer(false);
      });
    }
    document.querySelectorAll(".nav-sections a").forEach(function (link) {
      link.addEventListener("click", function () {
        showCurrentSection(link);
        setDrawer(false);
      });
    });

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape") {
        setDrawer(false);
      }
    });
  }

  function initLightbox() {
    var lightbox = document.getElementById("lightbox");
    var lightboxImage = document.getElementById("lightbox-image");
    var lightboxCaption = document.getElementById("lightbox-caption");
    var closeButton = document.getElementById("lightbox-close");
    var previousFocus = null;

    if (!lightbox || !lightboxImage || !closeButton) {
      return;
    }

    function closeLightbox() {
      lightbox.hidden = true;
      lightboxImage.removeAttribute("src");
      document.body.classList.remove("lightbox-open");
      if (previousFocus) {
        previousFocus.focus();
      }
    }

    document.querySelectorAll(".manual-figure img").forEach(function (image) {
      image.setAttribute("tabindex", "0");
      image.setAttribute("role", "button");
      image.setAttribute("aria-label", "点击放大这张截图");

      function openLightbox() {
        previousFocus = image;
        lightboxImage.src = image.currentSrc || image.src;
        lightboxImage.alt = image.alt;
        lightboxCaption.textContent = image.alt;
        lightbox.hidden = false;
        document.body.classList.add("lightbox-open");
        closeButton.focus();
      }

      image.addEventListener("click", openLightbox);
      image.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          openLightbox();
        }
      });
    });

    closeButton.addEventListener("click", closeLightbox);
    lightbox.addEventListener("click", function (event) {
      if (event.target === lightbox || event.target === lightboxImage) {
        closeLightbox();
      }
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && !lightbox.hidden) {
        closeLightbox();
      }
    });
  }

  function appendHighlightedText(container, text, query, className) {
    var lowerText = text.toLocaleLowerCase("zh-CN");
    var lowerQuery = query.toLocaleLowerCase("zh-CN");
    var offset = 0;
    var matchIndex = lowerText.indexOf(lowerQuery);

    if (!lowerQuery || matchIndex === -1) {
      container.appendChild(document.createTextNode(text));
      return;
    }

    while (matchIndex !== -1) {
      if (matchIndex > offset) {
        container.appendChild(
          document.createTextNode(text.slice(offset, matchIndex)),
        );
      }
      var mark = document.createElement("mark");
      mark.className = className;
      mark.textContent = text.slice(matchIndex, matchIndex + query.length);
      container.appendChild(mark);
      offset = matchIndex + query.length;
      matchIndex = lowerText.indexOf(lowerQuery, offset);
    }

    if (offset < text.length) {
      container.appendChild(document.createTextNode(text.slice(offset)));
    }
  }

  function initSearch() {
    var input = document.getElementById("site-search");
    var results = document.getElementById("search-results");
    var index = window.SEARCH_INDEX || [];

    if (!input || !results) {
      return;
    }

    function pageHref(item) {
      var prefix =
        document.body.dataset.pageType === "chapter" ? "../" : "";
      return prefix + item.url;
    }

    function resultSnippet(item, query) {
      var text = item.text.replace(/\s+/g, " ").trim();
      var matchIndex = text
        .toLocaleLowerCase("zh-CN")
        .indexOf(query.toLocaleLowerCase("zh-CN"));
      var snippetLength = 118;

      if (matchIndex === -1) {
        return text.slice(0, snippetLength) +
          (text.length > snippetLength ? "…" : "");
      }

      var start = Math.max(0, matchIndex - 42);
      var end = Math.min(
        text.length,
        matchIndex + query.length + snippetLength - 42,
      );
      return (
        (start > 0 ? "…" : "") +
        text.slice(start, end) +
        (end < text.length ? "…" : "")
      );
    }

    function renderResults(items, query) {
      results.replaceChildren();
      if (!query) {
        results.hidden = true;
        return;
      }
      results.hidden = false;

      if (!items.length) {
        var empty = document.createElement("p");
        empty.className = "search-empty";
        empty.textContent = "没有找到相关内容，请换一个关键词。";
        results.appendChild(empty);
        return;
      }

      items.slice(0, 10).forEach(function (item) {
        var link = document.createElement("a");
        var title = document.createElement("strong");
        var chapter = document.createElement("span");
        var snippet = document.createElement("p");
        link.className = "search-result";
        link.href =
          pageHref(item) + "?highlight=" + encodeURIComponent(query);
        title.textContent = item.title;
        chapter.textContent = item.chapter;
        snippet.className = "search-result-snippet";
        appendHighlightedText(
          snippet,
          resultSnippet(item, query),
          query,
          "search-snippet-highlight",
        );
        link.append(title, chapter, snippet);
        results.appendChild(link);
      });
    }

    input.addEventListener("input", function () {
      var query = input.value.trim();
      if (!query) {
        renderResults([], "");
        return;
      }
      var normalizedQuery = query.toLocaleLowerCase("zh-CN");
      var matches = index
        .filter(function (item) {
          return (
            item.title.toLocaleLowerCase("zh-CN").includes(normalizedQuery) ||
            item.chapter.toLocaleLowerCase("zh-CN").includes(normalizedQuery) ||
            item.text.toLocaleLowerCase("zh-CN").includes(normalizedQuery)
          );
        })
        .sort(function (left, right) {
          var leftTitle = left.title
            .toLocaleLowerCase("zh-CN")
            .includes(normalizedQuery);
          var rightTitle = right.title
            .toLocaleLowerCase("zh-CN")
            .includes(normalizedQuery);
          return Number(rightTitle) - Number(leftTitle);
        });
      renderResults(matches, query);
    });

    input.addEventListener("keydown", function (event) {
      if (event.key === "Enter") {
        var first = results.querySelector("a");
        if (first) {
          first.click();
        }
      } else if (event.key === "Escape") {
        input.value = "";
        renderResults([], "");
      }
    });

    document.addEventListener("click", function (event) {
      if (!results.contains(event.target) && event.target !== input) {
        results.hidden = true;
      }
    });
  }

  function initSearchHighlights() {
    var query = new URLSearchParams(window.location.search).get("highlight");
    if (!query) {
      return;
    }

    var roots = Array.from(
      document.querySelectorAll(".article-header h1, .article-body"),
    );
    var highlighted = false;

    roots.forEach(function (root) {
      var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
        acceptNode: function (node) {
          if (
            !node.nodeValue.trim() ||
            node.parentElement.closest(
              "script, style, .section-pagination, .manual-figure",
            )
          ) {
            return NodeFilter.FILTER_REJECT;
          }
          return node.nodeValue
            .toLocaleLowerCase("zh-CN")
            .includes(query.toLocaleLowerCase("zh-CN"))
            ? NodeFilter.FILTER_ACCEPT
            : NodeFilter.FILTER_REJECT;
        },
      });
      var textNodes = [];
      var node = walker.nextNode();
      while (node) {
        textNodes.push(node);
        node = walker.nextNode();
      }

      textNodes.forEach(function (textNode) {
        var fragment = document.createDocumentFragment();
        appendHighlightedText(
          fragment,
          textNode.nodeValue,
          query,
          "search-highlight",
        );
        textNode.replaceWith(fragment);
        highlighted = true;
      });
    });

    if (!highlighted) {
      return;
    }

    function clearHighlights() {
      document.querySelectorAll(".search-highlight").forEach(function (mark) {
        mark.replaceWith(document.createTextNode(mark.textContent));
      });
      roots.forEach(function (root) {
        root.normalize();
      });
      try {
        var cleanUrl = new URL(window.location.href);
        cleanUrl.searchParams.delete("highlight");
        history.replaceState(
          null,
          "",
          cleanUrl.pathname + cleanUrl.search + cleanUrl.hash,
        );
      } catch (error) {
        // Highlight clearing still works when file URLs restrict history changes.
      }
      highlighted = false;
    }

    requestAnimationFrame(function () {
      var firstHighlight = document.querySelector(".search-highlight");
      if (firstHighlight) {
        firstHighlight.scrollIntoView({
          behavior: "smooth",
          block: "center",
        });
      }
    });

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && highlighted) {
        clearHighlights();
      }
    });

    document.addEventListener("click", function (event) {
      if (
        highlighted &&
        !event.target.closest(
          ".search-highlight, a, button, input, summary, img",
        )
      ) {
        clearHighlights();
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initNavigation();
    initLightbox();
    initSearch();
    initSearchHighlights();
  });
})();
