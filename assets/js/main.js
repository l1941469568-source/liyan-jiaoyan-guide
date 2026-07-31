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
        link.className = "search-result";
        link.href = pageHref(item);
        title.textContent = item.title;
        chapter.textContent = item.chapter;
        link.append(title, chapter);
        results.appendChild(link);
      });
    }

    input.addEventListener("input", function () {
      var query = input.value.trim().toLocaleLowerCase("zh-CN");
      if (!query) {
        renderResults([], "");
        return;
      }
      var matches = index
        .filter(function (item) {
          return (
            item.title.toLocaleLowerCase("zh-CN").includes(query) ||
            item.chapter.toLocaleLowerCase("zh-CN").includes(query) ||
            item.text.toLocaleLowerCase("zh-CN").includes(query)
          );
        })
        .sort(function (left, right) {
          var leftTitle = left.title
            .toLocaleLowerCase("zh-CN")
            .includes(query);
          var rightTitle = right.title
            .toLocaleLowerCase("zh-CN")
            .includes(query);
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

  document.addEventListener("DOMContentLoaded", function () {
    initNavigation();
    initLightbox();
    initSearch();
  });
})();
