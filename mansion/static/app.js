function initTabGroup(root, tabSelector, panelSelector) {
  const tabs = root.querySelectorAll(tabSelector);
  const panels = root.querySelectorAll(panelSelector);
  if (!tabs.length || !panels.length) {
    return;
  }

  function showPanel(panel) {
    panels.forEach((item) => {
      item.classList.remove("active");
      item.hidden = true;
    });
    panel.classList.add("active");
    panel.hidden = false;
  }

  tabs.forEach((tab) => {
    if (tab.dataset.bound === "true") {
      return;
    }
    tab.dataset.bound = "true";

    tab.addEventListener("click", () => {
      tabs.forEach((item) => {
        item.classList.remove("active");
        item.setAttribute("aria-selected", "false");
      });

      tab.classList.add("active");
      tab.setAttribute("aria-selected", "true");

      const targetId = tab.dataset.tab || tab.dataset.pkTab;
      const panel = targetId
        ? root.querySelector(`#${CSS.escape(targetId)}`)
        : null;
      if (panel) {
        showPanel(panel);
      }
    });

    tab.setAttribute("role", "tab");
    tab.setAttribute(
      "aria-selected",
      tab.classList.contains("active") ? "true" : "false"
    );
  });

  panels.forEach((panel) => {
    panel.setAttribute("role", "tabpanel");
    panel.hidden = !panel.classList.contains("active");
  });
}

const house = document.querySelector(".house");
if (house) {
  initTabGroup(house, ".tab", ".tab-panel");

  const tabParam = new URLSearchParams(window.location.search).get("tab");
  if (tabParam) {
    const targetTab = house.querySelector(`.tab[data-tab="${CSS.escape(tabParam)}"]`);
    if (targetTab) {
      targetTab.click();
    }
  }
}

function initPkRooms(root = document) {
  root.querySelectorAll(".pk-room").forEach((room) => {
    initTabGroup(room, ".pk-tab", ".pk-panel");
  });
}

function openDialog(dialogId) {
  const dialog = document.getElementById(dialogId || "");
  if (!dialog || typeof dialog.showModal !== "function") {
    return;
  }
  dialog.showModal();
  initPkRooms(dialog);
}

document.querySelectorAll(".dialog-open, .room-edit-open, .pk-details-open").forEach((button) => {
  button.addEventListener("click", () => {
    openDialog(button.dataset.dialog);
  });
});

document.querySelectorAll(".room-dialog").forEach((dialog) => {
  const closeButton = dialog.querySelector(".dialog-close");
  if (closeButton) {
    closeButton.addEventListener("click", () => dialog.close());
  }
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) {
      dialog.close();
    }
  });
});

document.querySelectorAll("form[data-confirm]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    const message = form.dataset.confirm;
    if (message && !window.confirm(message)) {
      event.preventDefault();
    }
  });
});

const STATE_RANK = {
  open: 0,
  unlocked: 1,
  "internally locked": 2,
  "external lock": 3,
};

const layoutPages = {};

function layoutItems(board) {
  if (board.id === "map-board") {
    return [...board.querySelectorAll(".map-room")];
  }
  if (board.id === "room-grid") {
    return [...board.querySelectorAll(".room-card")];
  }
  return [...board.children];
}

function itemName(item) {
  return (item.dataset.name || item.querySelector("strong")?.textContent || "").toLowerCase();
}

function updateMapPositions(board) {
  board.querySelectorAll(".map-room:not([hidden])").forEach((item, index) => {
    const position = item.querySelector(".map-position");
    if (position) {
      position.textContent = String(index + 1);
    }
  });
}

function layoutPrefsKey(controlId) {
  return `mansion-layout-${controlId}`;
}

function loadLayoutPrefs(controlId) {
  try {
    return JSON.parse(localStorage.getItem(layoutPrefsKey(controlId)) || "{}");
  } catch {
    return {};
  }
}

function saveLayoutPrefs(controlId, prefs) {
  localStorage.setItem(layoutPrefsKey(controlId), JSON.stringify(prefs));
}

function getLayoutPage(controlId) {
  return layoutPages[controlId] || 1;
}

function setLayoutPage(controlId, page) {
  layoutPages[controlId] = Math.max(1, page);
}

function applyLayoutView(container, resetPage = false) {
  const board = document.getElementById(container.dataset.target || "");
  const controlId = container.dataset.controlId || container.dataset.target || "layout";
  if (!board) {
    return;
  }

  const select = container.querySelector(".layout-sort-select");
  const searchInput = container.querySelector(".layout-search");
  const activeFilter = container.querySelector(".layout-filter-btn.active");
  const sortBy = select?.value || "layout";
  const filter = activeFilter?.dataset.filter || "all";
  const query = (searchInput?.value || "").trim().toLowerCase();
  const pageSize = Number(container.dataset.pageSize || "0");
  const pagination = document.getElementById(`${controlId}-pagination`);
  const pageStatus = document.getElementById(`${controlId}-page-status`);

  if (resetPage) {
    setLayoutPage(controlId, 1);
  }

  const items = layoutItems(board);
  items.forEach((item, index) => {
    if (!item.dataset.layoutIndex) {
      item.dataset.layoutIndex = String(index);
    }
  });

  const matched = items.filter((item) => {
    const matchesFilter = filter === "all" || item.dataset.state === filter;
    const matchesSearch = !query || itemName(item).includes(query);
    return matchesFilter && matchesSearch;
  });

  matched.sort((left, right) => {
    if (sortBy === "layout") {
      return Number(left.dataset.layoutIndex) - Number(right.dataset.layoutIndex);
    }
    if (sortBy === "state") {
      const leftRank = STATE_RANK[left.dataset.state] ?? 99;
      const rightRank = STATE_RANK[right.dataset.state] ?? 99;
      if (leftRank !== rightRank) {
        return leftRank - rightRank;
      }
      return itemName(left).localeCompare(itemName(right));
    }
    if (sortBy === "name") {
      return itemName(left).localeCompare(itemName(right));
    }
    return 0;
  });

  let currentPage = getLayoutPage(controlId);
  const totalPages = pageSize > 0 ? Math.max(1, Math.ceil(matched.length / pageSize)) : 1;
  if (currentPage > totalPages) {
    currentPage = totalPages;
    setLayoutPage(controlId, currentPage);
  }

  const matchedSet = new Set(matched);
  items.forEach((item) => {
    if (!matchedSet.has(item)) {
      item.hidden = true;
    }
  });

  matched.forEach((item, index) => {
    if (!pageSize) {
      item.hidden = false;
    } else {
      const page = Math.floor(index / pageSize) + 1;
      item.hidden = page !== currentPage;
    }
    board.appendChild(item);
  });

  if (board.id === "map-board") {
    updateMapPositions(board);
  }

  if (pagination && pageStatus) {
    const showPagination = pageSize > 0 && matched.length > pageSize;
    pagination.hidden = !showPagination;
    pageStatus.textContent = showPagination
      ? `Page ${currentPage} of ${totalPages} · ${matched.length} rooms`
      : matched.length
        ? `${matched.length} room${matched.length === 1 ? "" : "s"}`
        : "No rooms match";
    pagination.querySelector('[data-page="prev"]').disabled = currentPage <= 1;
    pagination.querySelector('[data-page="next"]').disabled = currentPage >= totalPages;
  }

  saveLayoutPrefs(controlId, { sort: sortBy, filter, search: searchInput?.value || "" });
}

function initLayoutSort(container) {
  const controlId = container.dataset.controlId || container.dataset.target || "layout";
  const select = container.querySelector(".layout-sort-select");
  const searchInput = container.querySelector(".layout-search");
  const filters = container.querySelectorAll(".layout-filter-btn");
  const pagination = document.getElementById(`${controlId}-pagination`);
  const prefs = loadLayoutPrefs(controlId);

  if (select && prefs.sort) {
    select.value = prefs.sort;
  }
  if (searchInput && prefs.search) {
    searchInput.value = prefs.search;
  }
  if (prefs.filter) {
    filters.forEach((button) => {
      button.classList.toggle("active", button.dataset.filter === prefs.filter);
    });
  }

  if (select) {
    select.addEventListener("change", () => applyLayoutView(container, true));
  }

  if (searchInput) {
    searchInput.addEventListener("input", () => applyLayoutView(container, true));
  }

  filters.forEach((button) => {
    button.addEventListener("click", () => {
      filters.forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      applyLayoutView(container, true);
    });
  });

  if (pagination) {
    pagination.querySelectorAll(".page-btn").forEach((button) => {
      button.addEventListener("click", () => {
        const current = getLayoutPage(controlId);
        if (button.dataset.page === "prev") {
          setLayoutPage(controlId, current - 1);
        } else {
          setLayoutPage(controlId, current + 1);
        }
        applyLayoutView(container, false);
      });
    });
  }

  applyLayoutView(container, false);
}

document.querySelectorAll(".layout-sort").forEach(initLayoutSort);

const notes = document.querySelector("#private-notes");
if (notes && !notes.readOnly) {
  notes.value = localStorage.getItem("mansion-private-notes") || "";
  notes.addEventListener("input", () => {
    localStorage.setItem("mansion-private-notes", notes.value);
  });
}
