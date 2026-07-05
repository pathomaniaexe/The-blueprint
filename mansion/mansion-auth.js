(function () {
  // Demo passwords: owner = changeme, viewer = view-only
  // Replace these hashes before sharing your site publicly.
  // Run: python3 scripts/hash-password.py
  const OWNER_HASH =
    "pbkdf2_sha256$390000$PaQZnVGHdRXpRyOHroG_ag$jeBa73ow6USH2u0RJVyEmU6HKBMVZmnXbGXY__ZIMBM";
  const VIEWER_HASH =
    "pbkdf2_sha256$390000$m_Mv-GuV_cY8PZW5R4idsg$9Dw0nLebqaB7TIPlp4pcKzSLu6y7NpMd1451ybvRPeI";
  const SESSION_KEY = "mansion_session";
  const ROLE_LABELS = { owner: "Dev / owner / alter", viewer: "View only" };

  function b64ToBytes(data) {
    const padded = data + "=".repeat((4 - (data.length % 4)) % 4);
    const binary = atob(padded.replace(/-/g, "+").replace(/_/g, "/"));
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
    return bytes;
  }

  function bytesToB64(bytes) {
    let binary = "";
    bytes.forEach((b) => {
      binary += String.fromCharCode(b);
    });
    return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
  }

  async function passwordMatches(password, stored) {
    const [scheme, iterations, salt, expected] = stored.split("$");
    if (scheme !== "pbkdf2_sha256") return false;
    const keyMaterial = await crypto.subtle.importKey(
      "raw",
      new TextEncoder().encode(password),
      "PBKDF2",
      false,
      ["deriveBits"]
    );
    const derived = await crypto.subtle.deriveBits(
      {
        name: "PBKDF2",
        salt: b64ToBytes(salt),
        iterations: Number(iterations),
        hash: "SHA-256",
      },
      keyMaterial,
      256
    );
    return bytesToB64(new Uint8Array(derived)) === expected;
  }

  async function verifyPassword(password) {
    if (await passwordMatches(password, OWNER_HASH)) return "owner";
    if (await passwordMatches(password, VIEWER_HASH)) return "viewer";
    return null;
  }

  function applyRole(role) {
    document.body.dataset.role = role;
    const pill = document.getElementById("role-pill");
    if (pill) pill.textContent = ROLE_LABELS[role] || "Signed in";
    document.querySelectorAll("[data-owner-only]").forEach((el) => {
      el.hidden = role !== "owner";
    });
    const notes = document.getElementById("private-notes");
    if (notes) notes.readOnly = role !== "owner";
  }

  function showMansion(role) {
    const login = document.getElementById("login-view");
    const mansion = document.getElementById("mansion-view");
    if (login) login.hidden = true;
    if (mansion) mansion.hidden = false;
    applyRole(role);
    sessionStorage.setItem(SESSION_KEY, role);
  }

  function showLogin(message) {
    const login = document.getElementById("login-view");
    const mansion = document.getElementById("mansion-view");
    if (login) login.hidden = false;
    if (mansion) mansion.hidden = true;
    sessionStorage.removeItem(SESSION_KEY);
    const error = document.getElementById("login-error");
    if (error) {
      error.textContent = message || "";
      error.hidden = !message;
    }
  }

  async function handleLogin(event) {
    event.preventDefault();
    const input = document.getElementById("password");
    const password = input ? input.value : "";
    const role = await verifyPassword(password);
    if (!role) {
      showLogin("That password did not open the door.");
      return;
    }
    showMansion(role);
  }

  function handleLogout() {
    showLogin("");
    const input = document.getElementById("password");
    if (input) input.value = "";
  }

  document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("login-form");
    const lockBtn = document.getElementById("lock-site");
    if (form) form.addEventListener("submit", handleLogin);
    if (lockBtn) lockBtn.addEventListener("click", handleLogout);

    const saved = sessionStorage.getItem(SESSION_KEY);
    if (saved === "owner" || saved === "viewer") {
      showMansion(saved);
    } else {
      showLogin("");
    }
  });
})();
