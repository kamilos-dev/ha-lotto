// Lotto sidebar panel - plain Web Component, no build step.
// Home Assistant (panel_custom) instantiates this element and sets
// `.hass` / `.narrow` / `.panel` / `.route` on it directly.

class LottoPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._rules = null;
    this._coupons = [];
    this._loading = true;
    this._error = "";
    this._formError = "";
    this._selectedGame = "Lotto";
    this._selectedNumbers = [];
    this._selectedEuroNumbers = [];
    this._drawsTotal = 1;
    this._firstDrawDate = new Date().toISOString().slice(0, 10);
    this._narrow = false;
    this._unsubEventsPromise = null;
  }

  set hass(hass) {
    const isFirst = !this._hass;
    this._hass = hass;
    if (isFirst) {
      this._init();
    }
  }

  get hass() {
    return this._hass;
  }

  set narrow(value) {
    this._narrow = value;
    this._render();
  }

  connectedCallback() {
    this._render();
  }

  disconnectedCallback() {
    if (this._unsubEventsPromise) {
      this._unsubEventsPromise.then((unsub) => unsub());
      this._unsubEventsPromise = null;
    }
  }

  async _init() {
    try {
      const [rules, list] = await Promise.all([
        this._hass.callWS({ type: "lotto/get_rules" }),
        this._hass.callWS({ type: "lotto/list_coupons" }),
      ]);
      this._rules = rules;
      this._coupons = list.coupons;
    } catch (err) {
      this._error = `Nie udało się wczytać danych: ${err.message || err}`;
    }
    this._loading = false;
    this._render();

    this._unsubEventsPromise = this._hass.connection.subscribeEvents(
      () => this._refreshCoupons(),
      "lotto_updated"
    );
  }

  async _refreshCoupons() {
    try {
      const list = await this._hass.callWS({ type: "lotto/list_coupons" });
      this._coupons = list.coupons;
      this._render();
    } catch (err) {
      // Transient refresh failure - the next poll/event will retry.
    }
  }

  _toggleNumber(kind, n) {
    const rules = this._rules[this._selectedGame];
    const arr = kind === "main" ? this._selectedNumbers : this._selectedEuroNumbers;
    const max = kind === "main" ? rules.numbers_count : rules.euro_count;
    const idx = arr.indexOf(n);
    if (idx >= 0) {
      arr.splice(idx, 1);
    } else if (arr.length < max) {
      arr.push(n);
    }
    this._render();
  }

  _onGameChange(ev) {
    this._selectedGame = ev.target.value;
    this._selectedNumbers = [];
    this._selectedEuroNumbers = [];
    this._formError = "";
    this._render();
  }

  async _onSubmit(ev) {
    ev.preventDefault();
    this._formError = "";
    const rules = this._rules[this._selectedGame];

    if (this._selectedNumbers.length !== rules.numbers_count) {
      this._formError = `Wybierz dokładnie ${rules.numbers_count} liczb.`;
      this._render();
      return;
    }
    if (rules.euro_count && this._selectedEuroNumbers.length !== rules.euro_count) {
      this._formError = `Wybierz dokładnie ${rules.euro_count} liczb Euro.`;
      this._render();
      return;
    }
    if (!this._firstDrawDate) {
      this._formError = "Podaj datę pierwszego losowania.";
      this._render();
      return;
    }

    try {
      await this._hass.callWS({
        type: "lotto/add_coupon",
        game_type: this._selectedGame,
        numbers: this._selectedNumbers,
        euro_numbers: this._selectedEuroNumbers,
        draws_total: this._drawsTotal,
        first_draw_date: this._firstDrawDate,
      });
      this._selectedNumbers = [];
      this._selectedEuroNumbers = [];
      this._drawsTotal = 1;
      await this._refreshCoupons();
    } catch (err) {
      this._formError = (err && err.message) || String(err);
      this._render();
    }
  }

  async _deleteCoupon(id) {
    if (!confirm("Usunąć ten kupon?")) return;
    try {
      await this._hass.callWS({ type: "lotto/delete_coupon", coupon_id: id });
      await this._refreshCoupons();
    } catch (err) {
      this._error = (err && err.message) || String(err);
      this._render();
    }
  }

  _toggleSidebar() {
    this.dispatchEvent(new CustomEvent("hass-toggle-menu", { bubbles: true, composed: true }));
  }

  _numberGrid(kind, min, max, selected) {
    let html = `<div class="number-grid">`;
    for (let n = min; n <= max; n++) {
      const isSelected = selected.includes(n);
      html += `<button type="button" class="num-btn${isSelected ? " selected" : ""}" data-kind="${kind}" data-n="${n}">${n}</button>`;
    }
    html += `</div>`;
    return html;
  }

  _renderForm() {
    const rules = this._rules[this._selectedGame];
    return `
      <form id="add-form" class="card">
        <h2>Dodaj kupon</h2>
        <label>
          Typ losowania
          <select id="game-select">
            ${Object.keys(this._rules)
              .map(
                (g) =>
                  `<option value="${g}" ${g === this._selectedGame ? "selected" : ""}>${g}</option>`
              )
              .join("")}
          </select>
        </label>

        <div class="field-label">Liczby (${this._selectedNumbers.length}/${rules.numbers_count}), zakres ${rules.numbers_min}-${rules.numbers_max}</div>
        ${this._numberGrid("main", rules.numbers_min, rules.numbers_max, this._selectedNumbers)}

        ${
          rules.euro_count
            ? `
        <div class="field-label">Liczby Euro (${this._selectedEuroNumbers.length}/${rules.euro_count}), zakres ${rules.euro_min}-${rules.euro_max}</div>
        ${this._numberGrid("euro", rules.euro_min, rules.euro_max, this._selectedEuroNumbers)}
        `
            : ""
        }

        <div class="row">
          <label>
            Ważny na ile losowań
            <input id="draws-total" type="number" min="1" max="100" value="${this._drawsTotal}" />
          </label>
          <label>
            Pierwsza data losowania
            <input id="first-draw-date" type="date" value="${this._firstDrawDate}" />
          </label>
        </div>

        ${this._formError ? `<div class="error">${this._formError}</div>` : ""}

        <button type="submit" class="primary-btn">Dodaj kupon</button>
      </form>
    `;
  }

  _statusLabel(coupon) {
    const won = coupon.checked_draws.some((d) => d.is_win);
    if (won) return { text: "Wygrana!", cls: "badge-win" };
    if (coupon.status === "active") return { text: "Aktywny", cls: "badge-active" };
    return { text: "Zakończony", cls: "badge-expired" };
  }

  _renderCoupon(coupon) {
    const status = this._statusLabel(coupon);
    const numbers = coupon.numbers.join(", ");
    const euro = coupon.euro_numbers && coupon.euro_numbers.length ? ` + Euro: ${coupon.euro_numbers.join(", ")}` : "";
    const checks = coupon.checked_draws
      .slice()
      .reverse()
      .map((d) => {
        const detail =
          coupon.game_type === "EuroJackpot"
            ? `${d.matched_numbers} gł. + ${d.matched_euro_numbers} Euro`
            : `${d.matched_numbers} trafień`;
        return `<li class="${d.is_win ? "win" : ""}">${d.draw_date}: ${detail}${d.is_win ? " 🎉" : ""}</li>`;
      })
      .join("");

    return `
      <div class="card coupon">
        <div class="coupon-header">
          <span class="game-type">${coupon.game_type}</span>
          <span class="badge ${status.cls}">${status.text}</span>
          <button type="button" class="delete-btn" data-id="${coupon.id}" title="Usuń">✕</button>
        </div>
        <div class="coupon-numbers">${numbers}${euro}</div>
        <div class="coupon-meta">
          <div>Pierwsze losowanie: ${coupon.first_draw_date}</div>
          <div>Ilość losowań: ${coupon.draws_total}</div>
          <div>Pozostałe losowania: ${coupon.draws_remaining}</div>
        </div>
        ${checks ? `<ul class="checked-draws">${checks}</ul>` : ""}
      </div>
    `;
  }

  _render() {
    if (!this.shadowRoot) return;

    if (this._loading) {
      this.shadowRoot.innerHTML = `${this._styles()}<div class="loading">Wczytywanie…</div>`;
      return;
    }

    if (this._error) {
      this.shadowRoot.innerHTML = `${this._styles()}<div class="toolbar">${this._toolbar()}</div><div class="content"><div class="error">${this._error}</div></div>`;
      return;
    }

    const coupons = this._coupons.slice().sort((a, b) => (a.created_at < b.created_at ? 1 : -1));

    this.shadowRoot.innerHTML = `
      ${this._styles()}
      <div class="toolbar">${this._toolbar()}</div>
      <div class="content">
        ${this._renderForm()}
        <div class="card">
          <h2>Twoje kupony</h2>
          ${coupons.length ? coupons.map((c) => this._renderCoupon(c)).join("") : `<p class="empty">Brak kuponów. Dodaj pierwszy powyżej.</p>`}
        </div>
      </div>
    `;

    this._attachListeners();
  }

  _toolbar() {
    return `
      <button type="button" id="menu-btn" class="menu-btn" title="Menu">☰</button>
      <div class="toolbar-title">Lotto</div>
    `;
  }

  _attachListeners() {
    const root = this.shadowRoot;
    const menuBtn = root.getElementById("menu-btn");
    if (menuBtn) menuBtn.addEventListener("click", () => this._toggleSidebar());

    const form = root.getElementById("add-form");
    if (form) form.addEventListener("submit", (ev) => this._onSubmit(ev));

    const gameSelect = root.getElementById("game-select");
    if (gameSelect) gameSelect.addEventListener("change", (ev) => this._onGameChange(ev));

    const drawsTotal = root.getElementById("draws-total");
    if (drawsTotal)
      drawsTotal.addEventListener("change", (ev) => {
        this._drawsTotal = parseInt(ev.target.value, 10) || 1;
      });

    const firstDrawDate = root.getElementById("first-draw-date");
    if (firstDrawDate)
      firstDrawDate.addEventListener("change", (ev) => {
        this._firstDrawDate = ev.target.value;
      });

    root.querySelectorAll(".num-btn").forEach((btn) => {
      btn.addEventListener("click", () => this._toggleNumber(btn.dataset.kind, parseInt(btn.dataset.n, 10)));
    });

    root.querySelectorAll(".delete-btn").forEach((btn) => {
      btn.addEventListener("click", () => this._deleteCoupon(btn.dataset.id));
    });
  }

  _styles() {
    return `
      <style>
        :host {
          display: block;
          height: 100%;
          background: var(--primary-background-color, #fafafa);
          color: var(--primary-text-color, #212121);
          font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif);
          overflow-y: auto;
        }
        .toolbar {
          display: flex;
          align-items: center;
          height: 56px;
          padding: 0 16px;
          background: var(--app-header-background-color, var(--primary-color, #03a9f4));
          color: var(--app-header-text-color, #fff);
        }
        .menu-btn {
          background: none;
          border: none;
          color: inherit;
          font-size: 20px;
          cursor: pointer;
          padding: 8px;
          margin-right: 8px;
        }
        .toolbar-title {
          font-size: 20px;
          font-weight: 400;
        }
        .content {
          max-width: 720px;
          margin: 0 auto;
          padding: 16px;
        }
        .card {
          background: var(--card-background-color, #fff);
          border-radius: var(--ha-card-border-radius, 8px);
          box-shadow: var(--ha-card-box-shadow, 0 1px 3px rgba(0,0,0,0.12));
          padding: 16px;
          margin-bottom: 16px;
        }
        h2 {
          margin: 0 0 12px 0;
          font-size: 18px;
          font-weight: 500;
        }
        label {
          display: block;
          font-size: 13px;
          color: var(--secondary-text-color, #727272);
          margin-bottom: 12px;
        }
        select, input {
          display: block;
          width: 100%;
          box-sizing: border-box;
          margin-top: 4px;
          padding: 8px;
          font-size: 14px;
          border: 1px solid var(--divider-color, #e0e0e0);
          border-radius: 4px;
          background: var(--card-background-color, #fff);
          color: var(--primary-text-color, #212121);
        }
        .row {
          display: flex;
          gap: 16px;
        }
        .row label {
          flex: 1;
        }
        .field-label {
          font-size: 13px;
          color: var(--secondary-text-color, #727272);
          margin: 8px 0 4px 0;
        }
        .number-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(38px, 1fr));
          gap: 6px;
          margin-bottom: 8px;
        }
        .num-btn {
          height: 38px;
          border-radius: 50%;
          border: 1px solid var(--divider-color, #e0e0e0);
          background: var(--card-background-color, #fff);
          color: var(--primary-text-color, #212121);
          cursor: pointer;
          font-size: 13px;
        }
        .num-btn.selected {
          background: var(--primary-color, #03a9f4);
          color: #fff;
          border-color: var(--primary-color, #03a9f4);
        }
        .primary-btn {
          margin-top: 8px;
          padding: 10px 20px;
          border: none;
          border-radius: 4px;
          background: var(--primary-color, #03a9f4);
          color: #fff;
          font-size: 14px;
          cursor: pointer;
        }
        .error {
          color: var(--error-color, #db4437);
          margin: 8px 0;
          font-size: 14px;
        }
        .loading, .empty {
          padding: 32px;
          text-align: center;
          color: var(--secondary-text-color, #727272);
        }
        .coupon-header {
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .game-type {
          font-weight: 500;
        }
        .badge {
          font-size: 12px;
          padding: 2px 8px;
          border-radius: 12px;
          color: #fff;
        }
        .badge-active { background: var(--primary-color, #03a9f4); }
        .badge-expired { background: var(--disabled-text-color, #9e9e9e); }
        .badge-win { background: var(--success-color, #43a047); }
        .delete-btn {
          margin-left: auto;
          background: none;
          border: none;
          color: var(--secondary-text-color, #727272);
          cursor: pointer;
          font-size: 16px;
        }
        .coupon-numbers {
          margin-top: 8px;
          font-size: 16px;
          letter-spacing: 0.5px;
        }
        .coupon-meta {
          margin-top: 4px;
          font-size: 12px;
          color: var(--secondary-text-color, #727272);
        }
        .coupon-meta div {
          line-height: 1.6;
        }
        .checked-draws {
          margin: 8px 0 0 0;
          padding-left: 18px;
          font-size: 13px;
        }
        .checked-draws li.win {
          color: var(--success-color, #43a047);
          font-weight: 500;
        }
        .coupon + .coupon {
          margin-top: 12px;
        }
      </style>
    `;
  }
}

customElements.define("lotto-panel", LottoPanel);
