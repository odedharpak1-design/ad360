/* ==========================================================================
   AD360 — property-guide landing page
   Lead form handler: Netlify Forms (AJAX), UTM capture, dataLayer events,
   loading / success / error states, duplicate-submit prevention.
   ========================================================================== */
(function () {
  "use strict";

  var PDF_URL = "assets/downloads/ad360-madrich-chalukat-rechush-girushin.pdf";
  var THANK_YOU_URL = "thank-you.html";

  function encodeForm(data) {
    return Object.keys(data)
      .map(function (k) { return encodeURIComponent(k) + "=" + encodeURIComponent(data[k]); })
      .join("&");
  }

  function pushDataLayer(eventName, extra) {
    window.dataLayer = window.dataLayer || [];
    var payload = Object.assign({ event: eventName }, extra || {});
    window.dataLayer.push(payload);
  }

  function getUTMParams() {
    var params = new URLSearchParams(window.location.search);
    var keys = ["utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"];
    var out = {};
    keys.forEach(function (k) {
      out[k] = params.get(k) || "";
    });
    return out;
  }

  function fillHiddenUTMFields(form) {
    var utms = getUTMParams();
    Object.keys(utms).forEach(function (k) {
      var el = form.querySelector('[name="' + k + '"]');
      if (el) el.value = utms[k];
    });
    var submittedAt = form.querySelector('[name="submitted_at"]');
    if (submittedAt) submittedAt.value = new Date().toISOString();
  }

  function setState(card, state) {
    // state: 'idle' | 'loading' | 'success' | 'error'
    card.setAttribute("data-state", state);
  }

  function renderSuccess(card, downloadUrl) {
    card.innerHTML =
      '<div class="lp-form-success">' +
        '<div class="lp-form-success-icon">✓</div>' +
        '<div class="lp-form-title">תודה, המדריך שלכם מוכן</div>' +
        '<p class="lp-form-success-text">הפרטים התקבלו בהצלחה.<br>' +
        'הכנו עבורכם את המדריך לחלוקת רכוש בגירושין כדי לעזור לכם לראות את התמונה המלאה לפני שמקבלים החלטות משמעותיות.</p>' +
        '<a href="' + downloadUrl + '" class="lp-btn lp-btn-gold lp-btn-full lp-download-btn" download target="_blank" rel="noopener">הורידו את המדריך</a>' +
        '<div class="lp-form-note">הקובץ ייפתח בכרטיסייה חדשה.</div>' +
      '</div>';

    var dl = card.querySelector(".lp-download-btn");
    if (dl) {
      dl.addEventListener("click", function () {
        pushDataLayer("guide_download", { lead_magnet: "property_guide" });
      });
    }
  }

  function renderError(form, submitBtn, errorBox, message) {
    errorBox.textContent = message || "אירעה שגיאה בשליחת הפרטים. נסו שוב, ואם הבעיה חוזרת אפשר ליצור איתנו קשר בוואטסאפ.";
    errorBox.style.display = "block";
    submitBtn.disabled = false;
    submitBtn.textContent = "שלחו לי את המדריך";
  }

  function initForm(form) {
    var card = form.closest(".lp-form-card");
    var submitBtn = form.querySelector('button[type="submit"]');
    var errorBox = card.querySelector(".lp-form-error");
    var started = false;

    // fire guide_form_start once, on first interaction
    form.addEventListener("focusin", function () {
      if (!started) {
        started = true;
        pushDataLayer("guide_form_start", { lead_magnet: "property_guide" });
      }
    });

    form.addEventListener("submit", function (evt) {
      evt.preventDefault();

      if (submitBtn.disabled) return; // guard against double-submit
      submitBtn.disabled = true;
      submitBtn.textContent = "שולח...";
      setState(card, "loading");
      if (errorBox) errorBox.style.display = "none";

      fillHiddenUTMFields(form);

      var formData = new FormData(form);
      var payload = {};
      formData.forEach(function (value, key) { payload[key] = value; });

      fetch("/", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: encodeForm(payload),
      })
        .then(function (response) {
          if (!response.ok) throw new Error("network");
          setState(card, "success");
          pushDataLayer("guide_form_submit", {
            lead_magnet: "property_guide",
            form_location: "hero",
          });
          renderSuccess(card, PDF_URL);
        })
        .catch(function () {
          setState(card, "error");
          renderError(form, submitBtn, errorBox, null);
        });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var forms = document.querySelectorAll('form[data-netlify="true"]');
    forms.forEach(initForm);

    // landing_page_view fires once the page + tracking are ready
    pushDataLayer("landing_page_view", { lead_magnet: "property_guide" });
  });
})();
