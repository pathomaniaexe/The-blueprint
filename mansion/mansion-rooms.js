(function () {
  const OVERRIDES_KEY = "mansion_room_overrides";
  const ADDED_KEY = "mansion_added_rooms";
  const PLURALKIT_API = "https://api.pluralkit.me/v2";
  const ROOM_STATES = new Set(["open", "unlocked", "internally locked", "external lock"]);
  const STATE_OPTIONS = ["open", "unlocked", "internally locked", "external lock"];

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

  function loadAddedRooms() {
    try {
      const raw = localStorage.getItem(ADDED_KEY);
      const data = raw ? JSON.parse(raw) : [];
      return Array.isArray(data) ? data : [];
    } catch {
      return [];
    }
  }

  function saveAddedRooms(rooms) {
    localStorage.setItem(ADDED_KEY, JSON.stringify(rooms));
  }

  function bootstrapCount() {
    return loadBootstrapRooms().length;
  }

  function isAddedIndex(index) {
    return index >= bootstrapCount();
  }

  function addedSlot(index) {
    return index - bootstrapCount();
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function isPkRoom(room) {
    return Boolean(room && room.pk && typeof room.pk === "object");
  }

  function roomUuid(room) {
    if (!isPkRoom(room)) return "";
    return String(room.pk.uuid || "").trim();
  }

  function getEffectiveRoom(index) {
    const bootstrap = loadBootstrapRooms();
    if (index < bootstrap.length) {
      const base = bootstrap[index];
      if (!base) return null;
      const overrides = loadOverrides()[String(index)] || {};
      if (overrides._deleted) return null;
      const merged = { ...base, ...overrides };
      if (overrides.pk && typeof overrides.pk === "object") {
        merged.pk = overrides.pk;
      }
      return merged;
    }

    const added = loadAddedRooms();
    const room = added[addedSlot(index)];
    if (!room || room._deleted) return null;
    return { ...room };
  }

  function setOverride(index, patch) {
    if (isAddedIndex(index)) {
      const added = loadAddedRooms();
      const slot = addedSlot(index);
      if (!added[slot]) return;
      added[slot] = { ...added[slot], ...patch };
      saveAddedRooms(added);
      return;
    }
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

  function markRemoved(node) {
    node.hidden = true;
    node.setAttribute("aria-hidden", "true");
    node.dataset.removed = "true";
  }

  function markVisible(node) {
    node.hidden = false;
    node.removeAttribute("aria-hidden");
    delete node.dataset.removed;
  }

  function hideRoom(index) {
    document
      .querySelectorAll(`[data-layout-index="${index}"]`)
      .forEach((node) => markRemoved(node));
    document.getElementById(`pk-dialog-${index}`)?.remove();
    document.getElementById(`room-dialog-${index}`)?.remove();
    refreshSummaryCounts();
    refreshLayoutBoards();
  }

  function stateOptionsMarkup(selected) {
    return STATE_OPTIONS.map((state) => {
      const sel = state === selected ? " selected" : "";
      return `<option value="${escapeHtml(state)}"${sel}>${escapeHtml(state)}</option>`;
    }).join("\n");
  }

  function aboutText(room) {
    if (!isPkRoom(room)) return String(room.note || "");
    const note = String(room.note || "").trim();
    const description = String(room.pk.description || "").trim();
    if (note && note !== "Imported from PluralKit.") return note;
    return description || note || "Imported from PluralKit.";
  }

  function blurbMarkup(note) {
    const text = String(note || "");
    if (text.length <= 260) {
      return `<p class="room-card-blurb">${escapeHtml(text)}</p>`;
    }
    return `
    <details class="room-body-drawer">
      <summary>View note</summary>
      <p class="room-note">${escapeHtml(text)}</p>
    </details>`;
  }

  function safeImageUrl(url) {
    const value = String(url || "").trim();
    if (value.startsWith("https://") || value.startsWith("http://")) return value;
    return "";
  }

  function roomEditDialogMarkup(index, room) {
    const name = escapeHtml(room.name || "");
    const note = escapeHtml(aboutText(room));
    const state = ROOM_STATES.has(room.state) ? room.state : "unlocked";
    const pkHint = isPkRoom(room)
      ? '<p class="pk-edit-hint">PluralKit profile fields refresh on re-import. You can still rename the room and change lock state here.</p>'
      : "";
    const noteField = isPkRoom(room)
      ? `<input type="hidden" name="note" value="${note}">${pkHint}`
      : `<label class="wide">
          <span>Details</span>
          <textarea name="note" maxlength="4000" required>${note}</textarea>
        </label>`;
    return `
    <dialog class="room-dialog" id="room-dialog-${index}" data-owner-only>
      <div class="dialog-head">
        <h4>Edit ${name}</h4>
        <button type="button" class="dialog-close" aria-label="Close">×</button>
      </div>
      <form class="room-manage" method="post" action="/rooms/update">
        <input type="hidden" name="index" value="${index}">
        <label>
          <span>Name</span>
          <input name="name" maxlength="100" value="${name}" required>
        </label>
        <label>
          <span>State</span>
          <select name="state">${stateOptionsMarkup(state)}</select>
        </label>
        ${noteField}
        <div class="room-actions">
          <button type="submit" name="action" value="save">Save</button>
          <button type="submit" name="action" value="unlock">Unlock</button>
          <button type="submit" name="action" value="dormant">Dormant</button>
          <button type="submit" name="action" value="force">Force Lock</button>
          <button class="danger" type="submit" name="action" value="delete">Delete</button>
        </div>
      </form>
    </dialog>`;
  }

  function pkDetailsDialogMarkup(index, room) {
    if (!isPkRoom(room)) return "";
    const pk = room.pk;
    const name = escapeHtml(room.name || "Alter");
    const avatarUrl = safeImageUrl(pk.avatar_url);
    const bannerUrl = safeImageUrl(pk.banner);
    const rows = [
      ["PluralKit ID", pk.id],
      ["Display name", pk.display_name],
      ["Name", pk.name],
      ["Pronouns", pk.pronouns],
      ["Birthday", pk.birthday],
      ["Color", pk.color],
      ["Created", pk.created],
      ["Messages", pk.message_count],
    ]
      .filter(([, value]) => value !== undefined && value !== null && String(value).trim())
      .map(
        ([label, value]) =>
          `<div class="pk-field"><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(String(value))}</dd></div>`
      )
      .join("");
    const about = escapeHtml(aboutText(room));
    return `
    <dialog class="room-dialog pk-dialog" id="pk-dialog-${index}">
      <div class="dialog-head">
        <h4>${name}</h4>
        <button type="button" class="dialog-close" aria-label="Close">×</button>
      </div>
      <div class="pk-dialog-body">
        ${bannerUrl ? `<img class="pk-banner" src="${escapeHtml(bannerUrl)}" alt="" loading="lazy">` : ""}
        <div class="pk-dialog-profile">
          ${
            avatarUrl
              ? `<img class="pk-avatar" src="${escapeHtml(avatarUrl)}" alt="${name}" loading="lazy">`
              : ""
          }
          <dl class="pk-field-grid">${rows || '<p class="pk-empty">No profile fields imported.</p>'}</dl>
        </div>
        <div class="pk-description">${about || '<p class="pk-empty">No description.</p>'}</div>
      </div>
    </dialog>`;
  }

  function roomCardMarkup(index, room) {
    const name = escapeHtml(room.name || "");
    const state = escapeHtml(ROOM_STATES.has(room.state) ? room.state : "unlocked");
    const note = aboutText(room);
    const ownerOnly = document.body.dataset.role === "owner";
    const pk = isPkRoom(room);
    const avatarUrl = pk ? safeImageUrl(room.pk.avatar_url) : "";
    const pronouns = pk ? String(room.pk.pronouns || "").trim() : "";
    const birthday = pk ? String(room.pk.birthday || "").trim() : "";
    const metaBits = [pronouns, birthday].filter(Boolean).map(escapeHtml);
    const hiddenFields = `
      <input type="hidden" name="index" value="${index}">
      <input type="hidden" name="name" value="${name}">
      <input type="hidden" name="note" value="${escapeHtml(note)}">
      <input type="hidden" name="state" value="${state}">`;
    const pkButton = pk
      ? `<button type="button" class="pk-details-open" data-dialog="pk-dialog-${index}">PluralKit</button>`
      : "";
    const actions = `
      <div class="room-quick-actions">
        ${pkButton}
        ${
          ownerOnly
            ? `
        <button type="button" class="room-edit-open" data-dialog="room-dialog-${index}" data-owner-only>Edit</button>
        <form class="quick-form" method="post" action="/rooms/update" data-owner-only>
          ${hiddenFields}
          <button type="submit" name="action" value="unlock">Unlock</button>
        </form>
        <form class="quick-form" method="post" action="/rooms/update" data-owner-only>
          ${hiddenFields}
          <button type="submit" name="action" value="dormant">Dormant</button>
        </form>
        <form class="quick-form" method="post" action="/rooms/update" data-owner-only>
          ${hiddenFields}
          <button type="submit" name="action" value="force">Lock</button>
        </form>
        <form class="quick-form" method="post" action="/rooms/update" data-confirm="Delete this room?" data-owner-only>
          ${hiddenFields}
          <button class="danger" type="submit" name="action" value="delete">Delete</button>
        </form>
        ${roomEditDialogMarkup(index, room)}`
            : ""
        }
      </div>`;

    return `
    <article class="room-card ${pk ? "pk-room-card" : "room-card-manual"}" data-layout-index="${index}" data-name="${escapeHtml(
      String(room.name || "").toLowerCase()
    )}" data-state="${state}" ${pk ? 'data-source="pluralkit"' : 'data-local-added="true"'}>
      <div class="room-card-head">
        ${
          avatarUrl
            ? `<div class="room-avatar-wrap"><img class="room-avatar" src="${escapeHtml(
                avatarUrl
              )}" alt="${name}" loading="lazy" decoding="async"></div>`
            : ""
        }
        <div class="room-card-title">
          <div class="room-card-labels">
            <span class="room-state">${state}</span>
            ${pk ? '<span class="room-source">PluralKit</span>' : ""}
          </div>
          <h3>${name}</h3>
          ${metaBits.length ? `<p class="room-meta">${metaBits.join(" · ")}</p>` : ""}
        </div>
      </div>
      ${actions}
      ${blurbMarkup(note)}
      ${pkDetailsDialogMarkup(index, room)}
    </article>`;
  }

  function mapTileMarkup(index, room) {
    const name = escapeHtml(room.name || "");
    const state = escapeHtml(ROOM_STATES.has(room.state) ? room.state : "unlocked");
    const avatarUrl = isPkRoom(room) ? safeImageUrl(room.pk.avatar_url) : "";
    return `
    <article class="map-room" data-layout-index="${index}" data-name="${escapeHtml(
      String(room.name || "").toLowerCase()
    )}" data-state="${state}" data-local-added="true">
      <div class="map-room-top">
        <span class="map-position">${index + 1}</span>
        ${
          avatarUrl
            ? `<div class="map-avatar-wrap"><img class="map-avatar" src="${escapeHtml(
                avatarUrl
              )}" alt="${name}" loading="lazy"></div>`
            : ""
        }
      </div>
      <strong>${name}</strong>
      <small>${state}</small>
    </article>`;
  }

  function removeRoomDom(index) {
    document.querySelector(`.room-card[data-layout-index="${index}"]`)?.remove();
    document.querySelector(`.map-room[data-layout-index="${index}"]`)?.remove();
    document.getElementById(`pk-dialog-${index}`)?.remove();
    document.getElementById(`room-dialog-${index}`)?.remove();
  }

  function ensureRoomDom(index, room, forceReplace = false) {
    if (!room) {
      hideRoom(index);
      return;
    }

    if (forceReplace) {
      removeRoomDom(index);
    }

    const roomGrid = document.getElementById("room-grid");
    const mapBoard = document.getElementById("map-board");
    let card = document.querySelector(`.room-card[data-layout-index="${index}"]`);
    let map = document.querySelector(`.map-room[data-layout-index="${index}"]`);

    if (!card && roomGrid) {
      roomGrid.insertAdjacentHTML("beforeend", roomCardMarkup(index, room));
      card = document.querySelector(`.room-card[data-layout-index="${index}"]`);
      if (card && document.body.dataset.role !== "owner") {
        card.querySelectorAll("[data-owner-only]").forEach((el) => {
          el.hidden = true;
        });
      }
    }

    if (!map && mapBoard) {
      mapBoard.insertAdjacentHTML("beforeend", mapTileMarkup(index, room));
    }

    paintRoomDom(index, room);
  }

  function paintRoomDom(index, room) {
    const state = ROOM_STATES.has(room.state) ? room.state : "unlocked";
    const name = String(room.name || "");
    const note = aboutText(room);

    const card = document.querySelector(`.room-card[data-layout-index="${index}"]`);
    const map = document.querySelector(`.map-room[data-layout-index="${index}"]`);

    if (card) {
      markVisible(card);
      card.dataset.state = state;
      card.dataset.name = name.toLowerCase();
      const stateEl = card.querySelector(".room-state");
      if (stateEl) stateEl.textContent = state;
      const title = card.querySelector(".room-card-title h3");
      if (title) title.textContent = name;
      const dialogTitle = card.querySelector(`#room-dialog-${index} .dialog-head h4`);
      if (dialogTitle) dialogTitle.textContent = `Edit ${name}`;
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
      if (blurb) {
        if (note.length <= 260) {
          blurb.textContent = note;
          blurb.hidden = false;
        } else {
          blurb.hidden = true;
        }
      }
    }

    if (map) {
      markVisible(map);
      map.dataset.state = state;
      map.dataset.name = name.toLowerCase();
      const strong = map.querySelector("strong");
      if (strong) strong.textContent = name;
      const small = map.querySelector("small");
      if (small) small.textContent = state;
    }
  }

  function updateRoomCardDom(index, room) {
    if (!room) {
      hideRoom(index);
      return;
    }

    const card = document.querySelector(`.room-card[data-layout-index="${index}"]`);
    const map = document.querySelector(`.map-room[data-layout-index="${index}"]`);
    const needsPkShell =
      isPkRoom(room) && card && !card.classList.contains("pk-room-card");
    if (!card || !map || needsPkShell) {
      ensureRoomDom(index, room, Boolean(needsPkShell || !card || !map));
      return;
    }

    paintRoomDom(index, room);
  }

  function eachEffectiveRoom(callback) {
    const bootstrap = loadBootstrapRooms();
    bootstrap.forEach((_, index) => {
      callback(index, getEffectiveRoom(index));
    });
    loadAddedRooms().forEach((_, slot) => {
      const index = bootstrap.length + slot;
      callback(index, getEffectiveRoom(index));
    });
  }

  function indexByUuid() {
    const map = new Map();
    eachEffectiveRoom((index, room) => {
      if (!room) return;
      const uuid = roomUuid(room);
      if (uuid) map.set(uuid, index);
    });
    return map;
  }

  function memberToRoom(member, previousState) {
    const name = String(member.display_name || member.name || "").trim();
    if (!name) return null;
    const description = String(member.description || "").trim();
    const pronouns = String(member.pronouns || "").trim();
    const note = (description || pronouns || "Imported from PluralKit.").slice(0, 4000);
    const state =
      previousState && ROOM_STATES.has(previousState) ? previousState : "unlocked";
    return {
      name: name.slice(0, 100),
      state,
      note,
      source: "pluralkit",
      pk: member,
    };
  }

  function refreshSummaryCounts() {
    let total = 0;
    let open = 0;
    let dormant = 0;
    let forced = 0;

    eachEffectiveRoom((_, merged) => {
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

  function flashSaved(message) {
    let toast = document.getElementById("mansion-save-toast");
    if (!toast) {
      toast = document.createElement("p");
      toast.id = "mansion-save-toast";
      toast.className = "mansion-save-toast";
      document.body.appendChild(toast);
    }
    toast.textContent = message || "Saved in this browser.";
    toast.hidden = false;
    window.clearTimeout(flashSaved._timer);
    flashSaved._timer = window.setTimeout(() => {
      toast.hidden = true;
    }, 2800);
  }

  function handleRoomUpdate(form, submitter) {
    const data = parseRoomForm(form, submitter);
    if (data.index < 0 || Number.isNaN(data.index)) return;

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

    const existing = getEffectiveRoom(data.index) || {};
    const patch = { state };
    if (data.name) patch.name = data.name.slice(0, 100);
    if (data.note) patch.note = data.note.slice(0, 4000);
    if (data.action === "save") {
      const name = patch.name || existing.name;
      const note = patch.note || existing.note || aboutText(existing);
      if (!name || (!note && !isPkRoom(existing))) {
        window.alert("A room needs a name and details before saving.");
        return;
      }
      patch.name = String(name).slice(0, 100);
      if (note) patch.note = String(note).slice(0, 4000);
    }

    setOverride(data.index, patch);
    updateRoomCardDom(data.index, getEffectiveRoom(data.index));
    refreshSummaryCounts();
    refreshLayoutBoards();
    closeDialogForForm(form);
    flashSaved();
  }

  function handleAddRoom(form) {
    const data = parseRoomForm(form, null);
    if (!data.name || !data.note) {
      window.alert("A room needs a name and a note before it can be added.");
      return;
    }
    let state = data.state;
    if (!ROOM_STATES.has(state)) state = "unlocked";

    const room = {
      name: data.name.slice(0, 100),
      state,
      note: data.note.slice(0, 4000),
      source: "manual",
    };
    const added = loadAddedRooms();
    added.push(room);
    saveAddedRooms(added);

    const index = bootstrapCount() + added.length - 1;
    ensureRoomDom(index, room);
    refreshSummaryCounts();
    refreshLayoutBoards();
    closeDialogForForm(form);
    form.reset();
    flashSaved("Room added in this browser.");
  }

  async function fetchPluralkitMembers(token, systemRef) {
    const ref = encodeURIComponent(systemRef || "@me");
    // Do not set User-Agent — browsers treat it as a forbidden header.
    const response = await fetch(`${PLURALKIT_API}/systems/${ref}/members`, {
      headers: {
        Authorization: token,
        Accept: "application/json",
      },
    });
    if (!response.ok) {
      throw new Error(
        `PluralKit returned HTTP ${response.status}. Check the token, system ref, and member privacy.`
      );
    }
    const data = await response.json();
    if (!Array.isArray(data)) {
      throw new Error("PluralKit returned an unexpected response.");
    }
    return data.filter((item) => item && typeof item === "object");
  }

  function upsertPkMembers(members) {
    let addedCount = 0;
    let updatedCount = 0;
    let skipped = 0;
    const byUuid = indexByUuid();

    members.forEach((member) => {
      const uuid = String(member.uuid || "").trim();
      const existingIndex = uuid ? byUuid.get(uuid) : undefined;
      const previous =
        existingIndex !== undefined ? getEffectiveRoom(existingIndex) : null;
      const room = memberToRoom(member, previous?.state);
      if (!room) {
        skipped += 1;
        return;
      }

      if (existingIndex !== undefined) {
        setOverride(existingIndex, {
          name: room.name,
          note: room.note,
          source: "pluralkit",
          pk: room.pk,
          state: room.state,
        });
        ensureRoomDom(existingIndex, getEffectiveRoom(existingIndex), true);
        updatedCount += 1;
        return;
      }

      const addedRooms = loadAddedRooms();
      addedRooms.push(room);
      saveAddedRooms(addedRooms);
      const index = bootstrapCount() + addedRooms.length - 1;
      if (uuid) byUuid.set(uuid, index);
      ensureRoomDom(index, getEffectiveRoom(index), true);
      addedCount += 1;
    });

    return { addedCount, updatedCount, skipped };
  }

  async function handlePluralkitImport(form) {
    const fd = new FormData(form);
    const token = String(fd.get("token") || "").trim();
    const systemRef = String(fd.get("system_ref") || "@me").trim() || "@me";
    if (!token) {
      window.alert("PluralKit import needs a system token.");
      return;
    }

    const submit = form.querySelector('button[type="submit"]');
    const hint = form.querySelector(".pk-edit-hint");
    const originalHint = hint ? hint.textContent : "";
    if (submit) {
      submit.disabled = true;
      submit.textContent = "Importing…";
    }
    if (hint) {
      hint.textContent = "Talking to PluralKit… token is not saved.";
    }

    try {
      const members = await fetchPluralkitMembers(token, systemRef);
      const result = upsertPkMembers(members);
      refreshSummaryCounts();
      refreshLayoutBoards();
      closeDialogForForm(form);
      form.reset();
      const systemInput = form.querySelector('[name="system_ref"]');
      if (systemInput) systemInput.value = "@me";
      flashSaved(
        `PluralKit: ${result.addedCount} added, ${result.updatedCount} updated` +
          (result.skipped ? `, ${result.skipped} skipped` : "") +
          "."
      );
    } catch (err) {
      const message = err && err.message ? err.message : String(err);
      window.alert(message);
      if (hint) hint.textContent = originalHint || "Your token is used for this import only and is not saved.";
    } finally {
      if (submit) {
        submit.disabled = false;
        submit.textContent = "Import alters";
      }
    }
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
    eachEffectiveRoom((index, room) => {
      if (!room) {
        hideRoom(index);
        return;
      }
      if (isAddedIndex(index) || isPkRoom(room)) {
        ensureRoomDom(index, room, isAddedIndex(index));
      } else {
        updateRoomCardDom(index, room);
      }
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
        handlePluralkitImport(form);
        return;
      }
      if (action === "/rooms" || action.endsWith("/rooms")) {
        handleAddRoom(form);
        return;
      }
      handleRoomUpdate(form, event.submitter);
    },
    true
  );

  document.addEventListener("DOMContentLoaded", applyStoredRooms);
})();

