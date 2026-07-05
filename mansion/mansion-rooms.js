(function () {
  const OVERRIDES_KEY = "mansion_room_overrides";
  const ADDED_KEY = "mansion_added_rooms";
  const ROOM_STATES = new Set(["open", "unlocked", "internally locked", "external lock"]);

  function loadBootstrapRooms() {
    const el = document.getElementById("mansion-rooms-data");
    if (!el) return [];
    try {
      const data = JSON.parse(el.textContent || "[]");
      return Array.isArray(data) ? data : [];
    } catch {
      return [];
    }
  }

  function loadOverrides() {
    try {
      const raw = localStorage.getItem(OVERRIDES_KEY);
      return raw ? JSON.parse(raw) : {};
    } catch {
      return {};
    }
  }

  function saveOverrides(overrides) {
    localStorage.setItem(OVERRIDES_KEY, JSON.stringify(overrides));
  }

  function getEffectiveRoom(index) {
    const bootstrap = loadBootstrapRooms();
    const base = bootstrap[index];
    if (!base) return null;
    const overrides = loadOverrides()[String(index)] || {};
    if (overrides._deleted) return null;
    return { ...base, ...overrides };
  }

  function setOverride(index, patch) {
    const overrides = loadOverrides();
    const key = String(index);
    overrides[key] = { ...(overrides[key] || {}), ...patch };
    saveOverrides(overrides);
  }

  function parseRoomForm(form, submitter) {
    const fd = new FormData(form);
    const action =
      submitter?.getAttribute("value") ||
      submitter?.value ||
      fd.get("action") ||
      "save";
    return {
      index: Number.parseInt(String(fd.get("index") ?? "-1"), 10),
      action: String(action),
      name: String(fd.get("name") ?? "").trim(),
      state: String(fd.get("state") ?? "unlocked").trim(),
      note: String(fd.get("note") ?? "").trim(),
    };
  }

  function closeDialogForForm(form) {
    const dialog = form.closest("dialog");
    if (dialog && typeof dialog.close === "function") {
      dialog.close();
    }
  }

  function hideRoom(index) {
    document
      .querySelectorAll(`[data-layout-index="${index}"]`)
      .forEach((node) => {
        node.hidden = true;
        node.setAttribute("aria-hidden", "true");
      });
    document.getElementById(`pk-dialog-${index}`)?.remove();
    document.getElementById(`room-dialog-${index}`)?.remove();
    refreshSummaryCounts();
    refreshLayoutBoards();
  }

  function updateRoomCardDom(index, room) {
    if (!room) {
      hideRoom(index);
      return;
    }

    const state = ROOM_STATES.has(room.state) ? room.state : "unlocked";
    const name = String(room.name || "");
    const note = String(room.note || "");

    const card = document.querySelector(`.room-card[data-layout-index="${index}"]`);
    if (card) {
      card.hidden = false;
      card.removeAttribute("aria-hidden");
      card.dataset.state = state;
      card.dataset.name = name.toLowerCase();
      const stateEl = card.querySelector(".room-state");
      if (stateEl) stateEl.textContent = state;
      const title = card.querySelector(".room-card-title h3");
      if (title) title.textContent = name;
      card.querySelectorAll('input[name="name"]').forEach((input) => {
        if (input.type === "hidden" || input.type === "text") input.value = name;
      });
      card.querySelectorAll('input[name="state"]').forEach((input) => {
        if (input.type === "hidden") input.value = state;
      });
      card.querySelectorAll('input[name="note"]').forEach((input) => {
        if (input.type === "hidden") input.value = note;
      });
      card.querySelectorAll('textarea[name="note"]').forEach((area) => {
        area.value = note;
      });
      const select = card.querySelector('select[name="state"]');
      if (select) select.value = state;
      const blurb = card.querySelector(".room-card-blurb");
      if (blurb && note.length <= 260) blurb.textContent = note;
    }

    const map = document.querySelector(`.map-room[data-layout-index="${index}"]`);
    if (map) {
      map.hidden = false;
      map.removeAttribute("aria-hidden");
      map.dataset.state = state;
      map.dataset.name = name.toLowerCase();
      const strong = map.querySelector("strong");
      if (strong) strong.textContent = name;
      const small = map.querySelector("small");
      if (small) small.textContent = state;
    }
  }

  function refreshSummaryCounts() {
    const bootstrap = loadBootstrapRooms();
    const overrides = loadOverrides();
    let total = 0;
    let open = 0;
    let dormant = 0;
    let forced = 0;

    bootstrap.forEach((room, index) => {
      const merged = getEffectiveRoom(index);
      if (!merged) return;
      total += 1;
      const state = merged.state;
      if (state === "open" || state === "unlocked") open += 1;
      if (state === "internally locked") dormant += 1;
      if (state === "external lock") forced += 1;
    });

    const summary = document.querySelector(".house-summary");
    if (!summary) return;
    const blocks = summary.querySelectorAll("div");
    if (blocks[0]) blocks[0].querySelector("strong").textContent = String(total);
    if (blocks[1]) blocks[1].querySelector("strong").textContent = String(open);
    if (blocks[2]) blocks[2].querySelector("strong").textContent = String(dormant);
    if (blocks[3]) blocks[3].querySelector("strong").textContent = String(forced);
  }

  function refreshLayoutBoards() {
    document.querySelectorAll(".layout-sort").forEach((container) => {
      const select = container.querySelector(".layout-sort-select");
      if (select) {
        select.dispatchEvent(new Event("change", { bubbles: true }));
      }
    });
  }

  function flashSaved() {
    let toast = document.getElementById("mansion-save-toast");
    if (!toast) {
      toast = document.createElement("p");
      toast.id = "mansion-save-toast";
      toast.className = "mansion-save-toast";
      document.body.appendChild(toast);
    }
    toast.textContent = "Saved in this browser.";
    toast.hidden = false;
    window.clearTimeout(flashSaved._timer);
    flashSaved._timer = window.setTimeout(() => {
      toast.hidden = true;
    }, 2200);
  }

  function handleRoomUpdate(form, submitter) {
    const data = parseRoomForm(form, submitter);
    if (data.index < 0) return;

    if (data.action === "delete") {
      setOverride(data.index, { _deleted: true });
      hideRoom(data.index);
      flashSaved();
      return;
    }

    let state = data.state;
    if (data.action === "unlock") state = "unlocked";
    if (data.action === "dormant") state = "internally locked";
    if (data.action === "force") state = "external lock";
    if (!ROOM_STATES.has(state)) state = "unlocked";

    const patch = { state };
    if (data.name) patch.name = data.name.slice(0, 100);
    if (data.note) patch.note = data.note.slice(0, 4000);
    if (data.action === "save") {
      if (!patch.name || !patch.note) {
        window.alert("A room needs a name and details before saving.");
        return;
      }
    }

    setOverride(data.index, patch);
    updateRoomCardDom(data.index, getEffectiveRoom(data.index));
    refreshSummaryCounts();
    refreshLayoutBoards();
    closeDialogForForm(form);
    flashSaved();
  }

  function handleAddRoom(form, submitter) {
    const data = parseRoomForm(form, submitter);
    if (!data.name || !data.note) {
      window.alert("A room needs a name and a note before it can be added.");
      return;
    }
    let state = data.state;
    if (!ROOM_STATES.has(state)) state = "unlocked";
    const added = JSON.parse(localStorage.getItem(ADDED_KEY) || "[]");
    added.push({
      name: data.name.slice(0, 100),
      state,
      note: data.note.slice(0, 4000),
      source: "manual",
    });
    localStorage.setItem(ADDED_KEY, JSON.stringify(added));
    closeDialogForForm(form);
    window.alert("Room saved locally. Rebuild the site to show new rooms on every device.");
    flashSaved();
  }

  function isMansionForm(form) {
    const action = (form.getAttribute("action") || "").trim();
    return (
      action.endsWith("/rooms/update") ||
      action === "/rooms" ||
      action.endsWith("/rooms") ||
      action.endsWith("/pluralkit/import")
    );
  }

  function applyStoredRooms() {
    const bootstrap = loadBootstrapRooms();
    bootstrap.forEach((_, index) => {
      const room = getEffectiveRoom(index);
      if (!room) {
        hideRoom(index);
        return;
      }
      updateRoomCardDom(index, room);
    });
    refreshSummaryCounts();
    refreshLayoutBoards();
  }

  document.addEventListener(
    "submit",
    (event) => {
      const form = event.target;
      if (!(form instanceof HTMLFormElement) || !isMansionForm(form)) {
        return;
      }
      if (document.body.dataset.role !== "owner") {
        event.preventDefault();
        window.alert("View-only login cannot change rooms.");
        return;
      }
      event.preventDefault();

      const action = (form.getAttribute("action") || "").trim();
      if (action.endsWith("/pluralkit/import")) {
        window.alert("PluralKit import needs a server rebuild for now.");
        return;
      }
      if (action === "/rooms" || action.endsWith("/rooms")) {
        handleAddRoom(form, event.submitter);
        return;
      }
      handleRoomUpdate(form, event.submitter);
    },
    true
  );

  document.addEventListener("DOMContentLoaded", applyStoredRooms);
})();
