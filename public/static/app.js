const state = {
  products: [],
  activeView: "discover",
  parsedProduct: null,
  deviceId: getOrCreateDeviceId(),
  auth: {
    enabled: false,
    authenticated: false,
    user: null,
  },
  cart: JSON.parse(localStorage.getItem("almadan_cart") || "[]"),
  sharedListId: null,
  sharedListVersion: 0,
  optimizerMode: "single",
  theme: localStorage.getItem("almadan_theme") || "light",
  charts: {},
};

const currency = new Intl.NumberFormat("tr-TR", {
  style: "currency",
  currency: "TRY",
  maximumFractionDigits: 2,
});

const productFallbackIcons = {
  trendyol: "shopping-bag",
  hepsiburada: "package",
  amazon: "boxes",
  n11: "store",
  gratis: "flower",
  rossmann: "flower-2",
  supplementler: "dumbbell",
  proteinocean: "droplet",
  vatanbilgisayar: "cpu",
  itopya: "monitor",
  karaca: "home",
  lcwaikiki: "shirt",
  defacto: "shirt",
  mediamarkt: "smartphone",
  teknosa: "tv",
  zara: "shirt",
  migros: "shopping-cart",
  boyner: "shirt",
  koton: "shirt",
  mavi: "shirt",
  bim: "shopping-cart",
  a101: "shopping-cart",
  sok: "shopping-cart",
  file: "shopping-cart",
  metro: "shopping-cart",
  carrefoursa: "shopping-cart",
  manual: "package-search",
};

document.addEventListener("DOMContentLoaded", () => {
  applyTheme();
  lucide.createIcons();
  bindEvents();
  registerServiceWorker();
  updateNetworkStatus();
  const recoverySession = readRecoverySession();
  if (recoverySession) {
    showPasswordReset(recoverySession);
  }
  loadSession();
  loadProducts();
  checkSharedListUrl();
});

function bindEvents() {
  document.querySelectorAll("[data-view]").forEach((button) => {
    button.addEventListener("click", () => switchView(button.dataset.view));
  });

  document.getElementById("urlForm").addEventListener("submit", parseProduct);
  document.getElementById("pasteButton").addEventListener("click", pasteUrl);
  document.getElementById("refreshButton").addEventListener("click", refreshAllPrices);
  document.getElementById("dialogClose").addEventListener("click", closeDialog);
  document.getElementById("notificationButton").addEventListener("click", showNotifications);
  document.getElementById("accountButton").addEventListener("click", showAccount);
  
  document.getElementById("themeToggleButton").addEventListener("click", toggleTheme);
  document.getElementById("quickCartAddBtn").addEventListener("click", addQuickCartItem);
  document.getElementById("quickCartInput").addEventListener("keypress", (e) => {
    if (e.key === "Enter") addQuickCartItem();
  });
  document.getElementById("clearCartBtn").addEventListener("click", clearCart);
  document.getElementById("shareListBtn").addEventListener("click", shareCartList);
  document.getElementById("simulateBarcodeBtn").addEventListener("click", () => toggleScannerArea("barcode"));
  document.getElementById("simulateOcrBtn").addEventListener("click", () => toggleScannerArea("ocr"));
  document.getElementById("runBarcodeScanBtn").addEventListener("click", runBarcodeScan);
  document.getElementById("runOcrScanBtn").addEventListener("click", runOcrScan);
  document.getElementById("barcodeImageInput").addEventListener("change", scanBarcodeImage);
  document.getElementById("receiptImageInput").addEventListener("change", previewReceiptFile);
  document.getElementById("optModeSingle").addEventListener("click", () => switchOptimizerMode("single"));
  document.getElementById("optModeSplit").addEventListener("click", () => switchOptimizerMode("split"));
  document.getElementById("couponForm")?.addEventListener("submit", createCoupon);
  document.getElementById("micButton").addEventListener("click", startVoiceSearch);
  window.addEventListener("online", () => {
    updateNetworkStatus();
    flushPendingSharedSync();
  });
  window.addEventListener("offline", updateNetworkStatus);

  document.getElementById("productDialog").addEventListener("click", (event) => {
    if (event.target.id === "productDialog") closeDialog();
  });

  // Category Selector change listener
  const categorySelector = document.getElementById("searchCategorySelector");
  if (categorySelector) {
    categorySelector.addEventListener("change", handleCategoryChange);
  }

  // AI Selfie model buttons
  const btnSelfieLight = document.getElementById("btnSelfieLight");
  const btnSelfieMedium = document.getElementById("btnSelfieMedium");
  const btnSelfieDark = document.getElementById("btnSelfieDark");
  
  if (btnSelfieLight) btnSelfieLight.addEventListener("click", () => runAiSkinScan("light"));
  if (btnSelfieMedium) btnSelfieMedium.addEventListener("click", () => runAiSkinScan("medium"));
  if (btnSelfieDark) btnSelfieDark.addEventListener("click", () => runAiSkinScan("dark"));

  // Dropzone click triggers hidden file input
  const aiPhotoDropzone = document.getElementById("aiPhotoDropzone");
  if (aiPhotoDropzone) {
    aiPhotoDropzone.addEventListener("click", (e) => {
      if (e.target.closest("#aiSampleSelfies")) return;
      document.getElementById("aiPhotoFileInput").click();
    });
  }

  // Hidden file input change listener
  const aiPhotoFileInput = document.getElementById("aiPhotoFileInput");
  if (aiPhotoFileInput) {
    aiPhotoFileInput.addEventListener("change", () => {
      if (aiPhotoFileInput.files && aiPhotoFileInput.files[0]) {
        runAiSkinScan("uploaded");
      }
    });
  }

  // Question submission button
  const askAiColorBtn = document.getElementById("askAiColorBtn");
  if (askAiColorBtn) {
    askAiColorBtn.addEventListener("click", askAiColorSuitability);
  }
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-Device-ID": state.deviceId,
      ...(options.headers || {}),
    },
  });

  const contentType = response.headers.get("content-type") || "";
  const data = contentType.includes("application/json")
    ? await response.json()
    : { detail: await response.text() || `Sunucu hatası (${response.status})` };

  if (!response.ok) {
    throw new Error(apiErrorMessage(data, response.status));
  }
  return data;
}

async function loadSession() {
  try {
    state.auth = await api("/auth/session");
  } catch {
    state.auth = { enabled: false, authenticated: false, user: null };
  }
  renderAccountButton();
  handleCategoryChange();
}

function renderAccountButton() {
  const label = document.getElementById("accountButtonLabel");
  const button = document.getElementById("accountButton");
  if (!label || !button) return;

  if (state.auth.authenticated) {
    label.textContent = state.auth.user?.email?.split("@")[0] || "Hesabım";
    button.title = state.auth.user?.email || "Hesabım";
  } else {
    label.textContent = "Giriş";
    button.title = "Giriş yap veya hesap oluştur";
  }
}

let activeAuthMethod = "email"; // "email" or "sms"
let smsCodeSent = false;

function renderUnauthenticatedAuth(content) {
  if (activeAuthMethod === "email") {
    content.innerHTML = `
      <div class="dialog-body auth-dialog">
        <p class="eyebrow">ALMADAN HESABI</p>
        <h2>Takiplerini kaybetme.</h2>
        
        <div class="auth-tabs" style="display: flex; gap: 16px; margin-bottom: 20px; border-bottom: 1px solid var(--line); padding-bottom: 10px; width: 100%;">
          <button type="button" onclick="switchAuthMethod('email')" style="background: none; border: none; font-weight: bold; cursor: pointer; color: var(--green-dark); border-bottom: 2px solid var(--green-dark); padding-bottom: 8px; font-family: inherit; font-size: 14px;">E-posta ile Giriş</button>
          <button type="button" onclick="switchAuthMethod('sms')" style="background: none; border: none; cursor: pointer; color: var(--ink-light); padding-bottom: 8px; font-family: inherit; font-size: 14px;">SMS ile Giriş</button>
        </div>
        
        <p class="auth-copy" style="margin-bottom: 16px; font-size: 13px; color: var(--ink-light);">E-posta ile giriş yap. Bu cihazdaki ürünlerin hesabına otomatik taşınsın.</p>
        
        <div class="manual-fields">
          <label class="manual-field">
            <span>E-posta</span>
            <input id="authEmail" type="email" autocomplete="email" placeholder="ornek@email.com">
          </label>
          <label class="manual-field">
            <span>Şifre</span>
            <input id="authPassword" type="password" autocomplete="current-password" minlength="8" placeholder="En az 8 karakter">
          </label>
          <label class="manual-field">
            <span>Cinsiyet (Kişiselleştirilmiş Arama İçin)</span>
            <select id="authGender" style="width: 100%; min-height: 44px; padding: 0 12px; border: 1px solid var(--line); border-radius: 6px; background: white; font-family: inherit; font-size: 14px; color: var(--ink);">
              <option value="belirtilmemiş">Belirtilmemiş</option>
              <option value="erkek">Erkek</option>
              <option value="kadın">Kadın</option>
            </select>
          </label>
          <label class="manual-field">
            <span>Bildirim Tercihi</span>
            <select id="authNotificationPref" onchange="togglePhoneField()" style="width: 100%; min-height: 44px; padding: 0 12px; border: 1px solid var(--line); border-radius: 6px; background: white; font-family: inherit; font-size: 14px; color: var(--ink);">
              <option value="both">Hem SMS hem E-posta</option>
              <option value="email">Sadece E-posta</option>
              <option value="sms">Sadece SMS</option>
            </select>
          </label>
          <label id="phoneFieldLabel" class="manual-field">
            <span>Telefon Numarası</span>
            <input id="authPhone" type="tel" placeholder="05XXXXXXXXX">
          </label>
        </div>
        <button class="auth-link-button" type="button" onclick="showForgotPassword()">
          Şifremi unuttum
        </button>
        <p class="dialog-error" id="authError" hidden></p>
        ${state.auth.enabled ? `
          <div class="dialog-actions">
            <button class="secondary-button" type="button" onclick="submitAuth('signup')">Hesap oluştur</button>
            <button class="primary-button" type="button" onclick="submitAuth('login')">
              <i data-lucide="log-in"></i>
              Giriş yap
            </button>
          </div>
        ` : `
          <p class="dialog-error">Hesap sistemi henüz sunucuda etkinleştirilmedi.</p>
        `}
      </div>
    `;
  } else {
    content.innerHTML = `
      <div class="dialog-body auth-dialog">
        <p class="eyebrow">ALMADAN HESABI</p>
        <h2>SMS ile Hızlı Giriş.</h2>
        
        <div class="auth-tabs" style="display: flex; gap: 16px; margin-bottom: 20px; border-bottom: 1px solid var(--line); padding-bottom: 10px; width: 100%;">
          <button type="button" onclick="switchAuthMethod('email')" style="background: none; border: none; cursor: pointer; color: var(--ink-light); padding-bottom: 8px; font-family: inherit; font-size: 14px;">E-posta ile Giriş</button>
          <button type="button" onclick="switchAuthMethod('sms')" style="background: none; border: none; font-weight: bold; cursor: pointer; color: var(--green-dark); border-bottom: 2px solid var(--green-dark); padding-bottom: 8px; font-family: inherit; font-size: 14px;">SMS ile Giriş</button>
        </div>
        
        <p class="auth-copy" style="margin-bottom: 16px; font-size: 13px; color: var(--ink-light);">Şifresiz giriş yap. Telefonuna gelecek tek kullanımlık SMS koduyla hesabına anında ulaş.</p>
        
        <div class="manual-fields">
          <label class="manual-field">
            <span>Telefon Numarası</span>
            <input id="authSmsPhone" type="tel" placeholder="05XXXXXXXXX" ${smsCodeSent ? 'disabled' : ''}>
          </label>
          ${smsCodeSent ? `
            <label class="manual-field">
              <span>6 Haneli Doğrulama Kodu</span>
              <input id="authSmsCode" type="text" pattern="[0-9]*" inputmode="numeric" maxlength="6" placeholder="******">
            </label>
          ` : ''}
        </div>
        
        <p class="dialog-error" id="authError" hidden></p>
        
        ${state.auth.enabled ? `
          <div class="dialog-actions" style="margin-top: 20px;">
            ${smsCodeSent ? `
              <button class="secondary-button" type="button" onclick="resetSmsFlow()">Telefonu Değiştir</button>
              <button class="primary-button" type="button" onclick="verifySmsCode()">
                <i data-lucide="check"></i>
                Doğrula ve Giriş Yap
              </button>
            ` : `
              <button class="primary-button" type="button" onclick="sendSmsCode()" style="width: 100%;">
                <i data-lucide="send"></i>
                Kod Gönder
              </button>
            `}
          </div>
        ` : `
          <p class="dialog-error">Hesap sistemi henüz sunucuda etkinleştirilmedi.</p>
        `}
      </div>
    `;
  }
  lucide.createIcons();
  if (typeof togglePhoneField === "function" && activeAuthMethod === "email") togglePhoneField();
}

function switchAuthMethod(method) {
  activeAuthMethod = method;
  const content = document.getElementById("dialogContent");
  if (content) {
    renderUnauthenticatedAuth(content);
  }
}

function resetSmsFlow() {
  smsCodeSent = false;
  const content = document.getElementById("dialogContent");
  if (content) {
    renderUnauthenticatedAuth(content);
  }
}

async function sendSmsCode() {
  const phone = document.getElementById("authSmsPhone")?.value.trim();
  if (!phone || phone.length < 10) {
    showAuthError("Lütfen geçerli bir telefon numarası girin.");
    return;
  }
  
  try {
    const errorBox = document.getElementById("authError");
    if (errorBox) errorBox.hidden = true;
    
    await api("/auth/otp/send", {
      method: "POST",
      body: JSON.stringify({ phone }),
    });
    
    smsCodeSent = true;
    const content = document.getElementById("dialogContent");
    if (content) {
      renderUnauthenticatedAuth(content);
    }
    showToast("Doğrulama kodu gönderildi.");
  } catch (error) {
    showAuthError(error.message);
  }
}

async function verifySmsCode() {
  const phone = document.getElementById("authSmsPhone")?.value.trim();
  const code = document.getElementById("authSmsCode")?.value.trim();
  
  if (!phone || !code || code.length !== 6) {
    showAuthError("Lütfen 6 haneli doğrulama kodunu girin.");
    return;
  }
  
  try {
    const errorBox = document.getElementById("authError");
    if (errorBox) errorBox.hidden = true;
    
    const result = await api("/auth/otp/verify", {
      method: "POST",
      body: JSON.stringify({ phone, code }),
    });
    
    state.auth = {
      enabled: true,
      authenticated: true,
      user: result.user,
    };
    renderAccountButton();
    handleCategoryChange();
    closeDialog();
    await loadProducts();
    showToast("Giriş yapıldı.");
  } catch (error) {
    showAuthError(error.message);
  }
}

function showAccount() {
  const dialog = document.getElementById("productDialog");
  const content = document.getElementById("dialogContent");

  if (state.auth.authenticated) {
    content.innerHTML = `
      <div class="dialog-body auth-dialog">
        <p class="eyebrow">HESABIN</p>
        <h2>Takiplerin seninle gelsin.</h2>
        <div class="account-summary">
          <span class="account-avatar"><i data-lucide="user-round"></i></span>
          <div>
            <strong>${escapeHtml(state.auth.user?.email || state.auth.user?.phone || "Almadan kullanıcısı")}</strong>
            <p>Takiplerin bu hesapla farklı cihazlarda eşitlenir.</p>
          </div>
        </div>
        <div class="manual-fields">
          <label class="manual-field">
            <span>Cinsiyet</span>
            <select id="profileGender">
              <option value="belirtilmemiş">Belirtilmemiş</option>
              <option value="erkek" ${state.auth.user?.gender === "erkek" ? "selected" : ""}>Erkek</option>
              <option value="kadın" ${state.auth.user?.gender === "kadın" ? "selected" : ""}>Kadın</option>
            </select>
          </label>
          <label class="manual-field">
            <span>Bildirim Tercihi</span>
            <select id="profileNotificationPref" onchange="toggleProfilePhoneField()">
              <option value="both" ${state.auth.user?.notification_pref === "both" ? "selected" : ""}>Hem SMS hem E-posta</option>
              <option value="email" ${state.auth.user?.notification_pref === "email" ? "selected" : ""}>Sadece E-posta</option>
              <option value="sms" ${state.auth.user?.notification_pref === "sms" ? "selected" : ""}>Sadece SMS</option>
            </select>
          </label>
          <label class="manual-field" id="profilePhoneField">
            <span>Telefon Numarası</span>
            <input id="profilePhone" type="tel" value="${escapeHtml(state.auth.user?.phone || "")}" placeholder="05XXXXXXXXX">
          </label>
          <label class="profile-checkbox">
            <input id="profileSilenceEnabled" type="checkbox" ${state.auth.user?.silence_hours ? "checked" : ""}>
            <span>22:00-08:00 arasında bildirimleri sabaha ertele</span>
          </label>
        </div>
        <p class="dialog-error" id="authError" hidden></p>
        <button class="primary-button auth-submit-button" type="button" onclick="saveProfileSettings()">
          <i data-lucide="save"></i>
          Ayarları kaydet
        </button>
        <button class="danger-button" type="button" onclick="logoutAccount()">
          <i data-lucide="log-out"></i>
          Çıkış yap
        </button>
      </div>
    `;
  } else {
    smsCodeSent = false;
    renderUnauthenticatedAuth(content);
  }

  dialog.showModal();
  lucide.createIcons();
  if (typeof togglePhoneField === "function" && activeAuthMethod === "email") togglePhoneField();
  if (typeof toggleProfilePhoneField === "function") toggleProfilePhoneField();
}

function toggleProfilePhoneField() {
  const pref = document.getElementById("profileNotificationPref")?.value;
  const phoneField = document.getElementById("profilePhoneField");
  if (phoneField) phoneField.hidden = pref === "email";
}

async function saveProfileSettings() {
  const gender = document.getElementById("profileGender")?.value || "belirtilmemiş";
  const notificationPref = document.getElementById("profileNotificationPref")?.value || "both";
  const phone = document.getElementById("profilePhone")?.value.trim() || "";
  const silenceEnabled = Boolean(document.getElementById("profileSilenceEnabled")?.checked);

  if (notificationPref !== "email" && !phone) {
    showAuthError("SMS bildirimleri için telefon numarası gereklidir.");
    return;
  }

  try {
    const result = await api("/auth/profile", {
      method: "PUT",
      body: JSON.stringify({
        gender,
        phone,
        notification_pref: notificationPref,
        silence_enabled: silenceEnabled,
      }),
    });
    state.auth.user = result.user;
    closeDialog();
    showToast("Profil ve bildirim ayarların kaydedildi.");
  } catch (error) {
    showAuthError(error.message);
  }
}

function showForgotPassword() {
  const dialog = document.getElementById("productDialog");
  const content = document.getElementById("dialogContent");
  const currentEmail = document.getElementById("authEmail")?.value.trim() || "";

  content.innerHTML = `
    <div class="dialog-body auth-dialog">
      <p class="eyebrow">ŞİFRE YENİLEME</p>
      <h2>Hesabına yeniden ulaş.</h2>
      <p class="auth-copy">E-posta adresini yaz. Sana yeni şifre belirleyebileceğin güvenli bir bağlantı gönderelim.</p>
      <div class="manual-fields">
        <label class="manual-field">
          <span>E-posta</span>
          <input id="resetEmail" type="email" autocomplete="email" value="${escapeHtml(currentEmail)}" placeholder="ornek@email.com">
        </label>
      </div>
      <p class="dialog-error" id="authError" hidden></p>
      <div class="dialog-actions">
        <button class="secondary-button" type="button" onclick="showAccount()">Geri dön</button>
        <button class="primary-button" type="button" onclick="sendPasswordReset()">
          <i data-lucide="mail"></i>
          Bağlantı gönder
        </button>
      </div>
    </div>
  `;

  if (!dialog.open) dialog.showModal();
  lucide.createIcons();
  document.getElementById("resetEmail")?.focus();
}

async function sendPasswordReset() {
  const email = document.getElementById("resetEmail")?.value.trim();
  if (!email) {
    showAuthError("Geçerli bir e-posta adresi yaz.");
    return;
  }

  try {
    const result = await api("/auth/forgot-password", {
      method: "POST",
      body: JSON.stringify({ email }),
    });
    showToast(result.message || "Şifre yenileme bağlantısı gönderildi.");
    closeDialog();
  } catch (error) {
    showAuthError(error.message);
  }
}

function readRecoverySession() {
  if (!window.location.hash) return null;

  const params = new URLSearchParams(window.location.hash.slice(1));
  if (params.get("type") !== "recovery") return null;

  const accessToken = params.get("access_token");
  if (!accessToken) return null;

  return {
    accessToken,
    refreshToken: params.get("refresh_token"),
  };
}

function showPasswordReset(recoverySession) {
  const dialog = document.getElementById("productDialog");
  const content = document.getElementById("dialogContent");
  state.passwordRecovery = recoverySession;

  content.innerHTML = `
    <div class="dialog-body auth-dialog">
      <p class="eyebrow">YENİ ŞİFRE</p>
      <h2>Yeni şifreni belirle.</h2>
      <p class="auth-copy">En az 8 karakterli, başka hesaplarında kullanmadığın bir şifre seç.</p>
      <div class="manual-fields">
        <label class="manual-field">
          <span>Yeni şifre</span>
          <input id="newPassword" type="password" autocomplete="new-password" minlength="8" placeholder="En az 8 karakter">
        </label>
        <label class="manual-field">
          <span>Yeni şifre tekrar</span>
          <input id="newPasswordConfirm" type="password" autocomplete="new-password" minlength="8" placeholder="Şifreni tekrar yaz">
        </label>
      </div>
      <p class="dialog-error" id="authError" hidden></p>
      <button class="primary-button auth-submit-button" type="button" onclick="submitPasswordReset()">
        <i data-lucide="key-round"></i>
        Şifreyi yenile
      </button>
    </div>
  `;

  dialog.showModal();
  lucide.createIcons();
}

async function submitPasswordReset() {
  const password = document.getElementById("newPassword")?.value || "";
  const confirmation = document.getElementById("newPasswordConfirm")?.value || "";
  const recovery = state.passwordRecovery;

  if (!recovery?.accessToken) {
    showAuthError("Şifre yenileme bağlantısı geçersiz veya süresi dolmuş.");
    return;
  }
  if (password.length < 8) {
    showAuthError("Yeni şifre en az 8 karakter olmalı.");
    return;
  }
  if (password !== confirmation) {
    showAuthError("Yazdığın şifreler birbiriyle eşleşmiyor.");
    return;
  }

  try {
    const result = await api("/auth/reset-password", {
      method: "POST",
      body: JSON.stringify({
        access_token: recovery.accessToken,
        refresh_token: recovery.refreshToken,
        password,
      }),
    });

    history.replaceState(null, "", `${window.location.pathname}${window.location.search}`);
    state.passwordRecovery = null;
    state.auth = {
      enabled: true,
      authenticated: true,
      user: result.user,
    };
    renderAccountButton();
    closeDialog();
    showToast("Şifren yenilendi. Hesabına giriş yapıldı.");
  } catch (error) {
    showAuthError(error.message);
  }
}

async function submitAuth(mode) {
  const email = document.getElementById("authEmail")?.value.trim();
  const password = document.getElementById("authPassword")?.value || "";

  if (!email || password.length < 8) {
    showAuthError("Geçerli e-posta ve en az 8 karakterli şifre gerekli.");
    return;
  }

  const gender = document.getElementById("authGender")?.value || "belirtilmemiş";
  const notificationPref = document.getElementById("authNotificationPref")?.value || "both";
  const phone = document.getElementById("authPhone")?.value.trim() || "";

  if (mode === "signup" && notificationPref !== "email" && !phone) {
    showAuthError("SMS bildirimleri için telefon numarası gereklidir.");
    return;
  }

  try {
    const payload = { email, password };
    if (mode === "signup") {
      payload.gender = gender;
      payload.notification_pref = notificationPref;
      payload.phone = phone;
    }

    const result = await api(`/auth/${mode}`, {
      method: "POST",
      body: JSON.stringify(payload),
    });

    if (result.requires_email_confirmation) {
      showAuthError("Onay bağlantısı e-postana gönderildi. Onayladıktan sonra giriş yap.");
      return;
    }

    state.auth = {
      enabled: true,
      authenticated: true,
      user: result.user,
    };
    renderAccountButton();
    handleCategoryChange();
    closeDialog();
    await loadProducts();
    showToast(mode === "signup" ? "Hesabın oluşturuldu." : "Giriş yapıldı.");
  } catch (error) {
    showAuthError(error.message);
  }
}

function showAuthError(message) {
  const errorBox = document.getElementById("authError");
  if (!errorBox) return;
  errorBox.textContent = message;
  errorBox.hidden = false;
}

async function logoutAccount() {
  try {
    await api("/auth/logout", { method: "POST" });
    state.auth = { enabled: true, authenticated: false, user: null };
    renderAccountButton();
    closeDialog();
    await loadProducts();
    showToast("Çıkış yapıldı.");
  } catch (error) {
    showToast(error.message);
  }
}

function apiErrorMessage(data, status) {
  const detail = data?.detail ?? data?.message ?? data;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (detail && typeof detail.message === "string") return detail.message;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => item?.msg || item?.message || String(item))
      .join(" ");
  }
  return `İşlem tamamlanamadı (HTTP ${status}).`;
}

function proxiedImageUrl(url) {
  return `/image-proxy?url=${encodeURIComponent(url)}`;
}

function imageFallback(element, icon = "package-search") {
  const placeholder = document.createElement("span");
  placeholder.className = "product-placeholder";
  placeholder.innerHTML = `<i data-lucide="${icon}"></i>`;
  element.replaceWith(placeholder);
  lucide.createIcons();
}

async function loadProducts() {
  const grid = document.getElementById("dealGrid");
  grid.innerHTML = `<div class="loading-state"><span class="spinner"></span>Fırsatlar hazırlanıyor</div>`;

  try {
    state.products = await api("/products");
    renderAll();
  } catch (error) {
    grid.innerHTML = `<div class="empty-state">Ürünler yüklenemedi.<br>${escapeHtml(error.message)}</div>`;
  }
}

function renderAll() {
  renderDeals();
  renderTracking();
  renderSavings();
  lucide.createIcons();
}

function renderDeals() {
  const grid = document.getElementById("dealGrid");
  const products = [...state.products].sort((a, b) => b.deal_score - a.deal_score).slice(0, 6);

  if (!products.length) {
    grid.innerHTML = `<div class="empty-state"><i data-lucide="scan-search"></i>İlk ürün linkini ekleyerek fırsat radarını başlat.</div>`;
    return;
  }

  grid.innerHTML = products.map((product) => {
    const discountPercent = product.discount_analysis?.discount_percent || 0;
    const discountBadge = discountPercent > 0 
      ? `<span class="discount-badge">-%${discountPercent}</span>` 
      : "";
    const forecast = product.discount_forecast;
    const forecastBadge = forecast?.status === "ready"
      ? `<span class="forecast-chip">%${forecast.probability} · 7 gün</span>`
      : `<span class="forecast-chip muted">Tahmin hazırlanıyor</span>`;
    return `
    <article class="deal-card">
      <div class="deal-image">
        ${productImage(product)}
        <span class="score-badge">${product.deal_score}/100</span>
        ${discountBadge}
      </div>
      <div class="deal-body">
        <p class="source-name">${escapeHtml(product.source)}</p>
        <h3>${escapeHtml(product.title)}</h3>
        ${forecastBadge}
        <div class="price-row">
          <span class="price">${currency.format(product.current_price)}</span>
          <span class="verdict ${product.verdict === "bekle" ? "wait" : ""}">${escapeHtml(product.verdict)}</span>
        </div>
        <button class="card-button" onclick="openProduct('${product.id}')">Kararı gör</button>
      </div>
    </article>
  `;
  }).join("");
}

function renderTracking() {
  const list = document.getElementById("trackingList");
  document.getElementById("trackingCount").textContent = `${state.products.length} ürün`;

  if (!state.products.length) {
    list.innerHTML = `<div class="empty-state">Henüz takip edilen ürün yok.</div>`;
    return;
  }

  list.innerHTML = state.products.map((product) => {
    const firstPrice = product.price_history[0]?.price || product.current_price;
    const difference = Math.max(0, firstPrice - product.current_price);
    const discountPercent = product.discount_analysis?.discount_percent || 0;
    const forecast = product.discount_forecast;
    return `
      <button class="tracking-item" onclick="openProduct('${product.id}')">
        <span class="tracking-thumb">${productImage(product)}</span>
        <span class="tracking-copy">
          <h3>${escapeHtml(product.title)}</h3>
          <p>${escapeHtml(product.source)} · ${product.price_history.length} fiyat kaydı</p>
          <span class="check-status">
            <span class="status-dot ${escapeHtml(product.last_check_status || "pending")}"></span>
            ${escapeHtml(checkStatusText(product))}
          </span>
          <span class="tracking-forecast">
            ${forecast?.status === "ready"
              ? `7 günlük indirim ihtimali: %${forecast.probability}`
              : escapeHtml(forecast?.message || "Tahmin için fiyat geçmişi bekleniyor.")}
          </span>
        </span>
        <span class="tracking-price">
          <strong>${currency.format(product.current_price)}</strong>
          <span>${difference > 0 ? currency.format(difference) + " düştü" : "Takipte"}</span>
          ${discountPercent > 0 ? `<span class="discount-badge" style="position: static; display: inline-block; margin-top: 4px; padding: 2px 5px; font-size: 10px;">-%${discountPercent}</span>` : ""}
        </span>
      </button>
    `;
  }).join("");
}

function renderSavings() {
  const totalSavings = state.products.reduce((total, product) => {
    const firstPrice = product.price_history[0]?.price || product.current_price;
    return total + Math.max(0, firstPrice - product.current_price);
  }, 0);

  const buySignals = state.products.filter((product) => product.verdict === "al").length;
  const bestScore = state.products.reduce((best, product) => Math.max(best, product.deal_score), 0);

  document.getElementById("totalSavings").textContent = currency.format(totalSavings);
  document.getElementById("trackedStat").textContent = state.products.length;
  document.getElementById("buyStat").textContent = buySignals;
  document.getElementById("bestScoreStat").textContent = bestScore;
  renderSavingsCharts();
}

function destroyChart(name) {
  if (!state.charts[name]) return;
  state.charts[name].destroy();
  delete state.charts[name];
}

function renderSavingsCharts() {
  if (typeof Chart === "undefined") return;

  const productCanvas = document.getElementById("savingsProductChart");
  const categoryCanvas = document.getElementById("spendingCategoryChart");
  if (!productCanvas || !categoryCanvas) return;

  const productSavings = state.products
    .map((product) => ({
      label: product.title.length > 24 ? `${product.title.slice(0, 24)}…` : product.title,
      value: Math.max(
        0,
        (product.price_history[0]?.price || product.current_price) - product.current_price,
      ),
    }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 6);

  const categoryTotals = {};
  state.products.forEach((product) => {
    const category = getItemCategory(product.title);
    categoryTotals[category] = (categoryTotals[category] || 0) + product.current_price;
  });

  const categoryLabels = {
    grocery: "Market",
    electronics: "Elektronik",
    fashion: "Giyim",
    cosmetics: "Kozmetik",
    supplement: "Takviye",
  };
  const chartText = state.theme === "dark" ? "#c8cec8" : "#687068";
  const chartGrid = state.theme === "dark" ? "#2b3036" : "#e2e6df";

  destroyChart("products");
  destroyChart("categories");

  state.charts.products = new Chart(productCanvas, {
    type: "bar",
    data: {
      labels: productSavings.length
        ? productSavings.map((item) => item.label)
        : ["Henüz veri yok"],
      datasets: [{
        label: "Tasarruf",
        data: productSavings.length ? productSavings.map((item) => item.value) : [0],
        backgroundColor: "#287a50",
        borderRadius: 6,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ticks: { color: chartText }, grid: { display: false } },
        y: { ticks: { color: chartText }, grid: { color: chartGrid } },
      },
    },
  });

  const categoryEntries = Object.entries(categoryTotals);
  state.charts.categories = new Chart(categoryCanvas, {
    type: "doughnut",
    data: {
      labels: categoryEntries.length
        ? categoryEntries.map(([category]) => categoryLabels[category] || category)
        : ["Henüz veri yok"],
      datasets: [{
        data: categoryEntries.length ? categoryEntries.map(([, value]) => value) : [1],
        backgroundColor: ["#287a50", "#3979a8", "#c45243", "#8e5fa2", "#d39a32"],
        borderWidth: 0,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "66%",
      plugins: {
        legend: {
          position: "bottom",
          labels: { color: chartText, boxWidth: 10 },
        },
      },
    },
  });
}

function isUrl(string) {
  const s = string.trim().toLowerCase();
  return s.startsWith("http://") || s.startsWith("https://") || s.startsWith("trendyol://") || s.startsWith("hepsiburada://") || s.startsWith("n11://") || s.includes(".com") || s.includes(".net") || s.includes(".org") || s.includes(".co");
}

async function parseProduct(event) {
  event.preventDefault();
  const input = document.getElementById("productUrl");
  const submit = event.submitter;
  const val = input.value.trim();

  if (!val) return;

  submit.disabled = true;
  submit.innerHTML = `<span class="spinner"></span> İnceleniyor`;

  try {
    if (isUrl(val)) {
      const parsed = await api("/parse-url", {
        method: "POST",
        body: JSON.stringify({ url: val }),
      });
      showParsedProduct(parsed);
    } else {
      const category = document.getElementById("searchCategorySelector")?.value || "general";
      const results = await api(
        "/api/search?query=" + encodeURIComponent(val)
        + "&category=" + encodeURIComponent(category)
      );
      showSearchResults(results);
    }
  } catch (error) {
    showToast(error.message);
  } finally {
    submit.disabled = false;
    submit.innerHTML = `<i data-lucide="scan-search"></i> Kontrol et`;
    lucide.createIcons();
  }
}

function showSearchResults(response) {
  const dialog = document.getElementById("productDialog");
  const content = document.getElementById("dialogContent");
  
  const products = response.products || [];
  const suggestion = response.suggestion;
  const originalQuery = response.query || "";

  if (!products || products.length === 0) {
    let suggestionHtml = "";
    if (suggestion) {
      suggestionHtml = `
        <p style="margin-top: 16px; font-size: 15px; color: var(--ink);">
          Bunu mu demek istediniz: 
          <a href="#" style="color: var(--green); font-weight: 700; text-decoration: underline;" onclick="event.preventDefault(); triggerSuggestionSearch('${escapeHtml(suggestion)}');">
            ${escapeHtml(suggestion)}
          </a>
        </p>
      `;
    }
    content.innerHTML = `
      <div class="dialog-body" style="text-align: center; padding: 40px 20px;">
        <i data-lucide="frown" style="width: 48px; height: 48px; color: var(--muted); margin-bottom: 16px;"></i>
        <h2>Arama Sonucu Bulunamadı</h2>
        <p style="color: var(--muted); margin-top: 8px;">"${escapeHtml(originalQuery)}" için alternatif satıcı veya fiyat bilgisi bulunamadı.</p>
        ${suggestionHtml}
        <button class="secondary-button" style="margin-top: 24px;" onclick="closeDialog()">Kapat</button>
      </div>
    `;
    if (!dialog.open) dialog.showModal();
    lucide.createIcons();
    return;
  }

  const isFallback = response.fallback_applied;
  const fallbackNoticeHtml = isFallback
    ? `
      <div class="assistant-info-box" style="border-left: 3px solid var(--red); background: rgba(248, 215, 211, 0.1); margin-bottom: 16px;">
        <div class="assistant-info-title" style="color: #d9383a; font-weight: 700;">
          <i data-lucide="info"></i> Tam Eşleşme Bulunamadı
        </div>
        <div class="assistant-info-content" style="color: var(--ink);">
          "${escapeHtml(originalQuery)}" için tam eşleşen ürün bulunamadı. Size en yakın popüler alternatifleri listeliyoruz.
        </div>
      </div>
    `
    : "";

  content.innerHTML = `
    <style>
      .search-result-card {
        transition: all 0.2s ease-in-out;
      }
      .search-result-card:hover {
        border-color: var(--green) !important;
        box-shadow: 0 4px 12px rgba(40, 122, 80, 0.08);
        transform: translateY(-1px);
      }
    </style>
    <div class="dialog-body" style="max-width: 600px; width: 100%;">
      <p class="eyebrow" style="color: var(--green); font-weight: 700;">ARAMA SONUÇLARI</p>
      <h2 style="margin-bottom: 16px;">En Mantıklı Seçenekler</h2>
      ${fallbackNoticeHtml}
      <div style="display: flex; flex-direction: column; gap: 12px; max-height: 400px; overflow-y: auto; padding-right: 4px; margin-bottom: 24px;">
        ${products.map((item, index) => {
          const badgesHtml = item.labels.map(lbl => {
            let colorClass = "bg-gray";
            if (lbl === "En Ucuz") colorClass = "bg-green";
            if (lbl === "En Yüksek İndirim") colorClass = "bg-red";
            if (lbl === "Hızlı Kargo") colorClass = "bg-blue";
            if (lbl === "En İyi Puan") colorClass = "bg-yellow";
            if (lbl === "Şüpheli Fiyat") colorClass = "bg-red";
            return `<span class="analysis-status-badge ${colorClass}" style="font-size: 10px; padding: 2px 6px; border-radius: 4px; font-weight: 700; text-transform: uppercase;">${escapeHtml(lbl)}</span>`;
          }).join(" ");

          const originalPriceHtml = item.original_price && item.original_price > item.price
            ? `<span style="text-decoration: line-through; color: var(--muted); font-size: 11px; margin-right: 6px;">${currency.format(item.original_price)}</span>`
            : "";

          const isOutOfStock = item.extra_info?.out_of_stock;
          const priceDisplayHtml = isOutOfStock
            ? `<strong style="font-size: 14px; color: var(--muted); font-style: italic;">Stokta Yok</strong>`
            : `<strong style="font-size: 14px; color: var(--ink);">${currency.format(item.price)}</strong>`;

          const buttonHtml = isOutOfStock
            ? `<button class="primary-button" style="padding: 6px 12px; font-size: 11px; height: auto; width: auto; background-color: #687068; border-color: #687068;" onclick="trackSearchResultProduct(this, ${index})">
                 <i data-lucide="bell" style="width:12px; height:12px; margin-right:4px;"></i> Stok Takibi Ekle
               </button>`
            : `<button class="primary-button" style="padding: 6px 12px; font-size: 11px; height: auto; width: auto;" onclick="trackSearchResultProduct(this, ${index})">
                 <i data-lucide="radar" style="width:12px; height:12px; margin-right:4px;"></i> Radara Ekle
               </button>`;

          const suspiciousWarningHtml = item.extra_info?.suspicious
            ? `<div style="display: flex; align-items: center; gap: 4px; color: var(--red); font-size: 11px; margin-top: 6px; font-weight: 700;">
                 <i data-lucide="shield-alert" style="width: 13px; height: 13px; flex-shrink: 0;"></i> Şüpheli Fiyat Uyarısı!
               </div>`
            : "";
          const unitPriceHtml = item.extra_info?.unit_price && item.extra_info?.unit
            ? `<div class="unit-price-row ${item.extra_info.best_unit_price ? "best" : ""}">
                 ${currency.format(item.extra_info.unit_price)} / ${escapeHtml(item.extra_info.unit)}
               </div>`
            : "";

          return `
            <div class="search-result-card" style="display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px; border: 1px solid var(--line); border-radius: 8px; background: white; transition: all 0.2s;">
              <div style="width: 50px; height: 50px; flex-shrink: 0; border-radius: 6px; overflow: hidden; border: 1px solid var(--line); background: var(--surface); display: flex; align-items: center; justify-content: center;">
                ${item.image_url 
                  ? `<img src="${escapeHtml(proxiedImageUrl(item.image_url))}" alt="${escapeHtml(item.title)}" style="width: 100%; height: 100%; object-fit: contain;" onerror="imageFallback(this, '${productFallbackIcons[item.source] || "package-search"}')">`
                  : `<span class="product-placeholder" style="width:100%; height:100%; display:grid; place-items:center;"><i data-lucide="${productFallbackIcons[item.source] || "package-search"}" style="width:18px; height:18px;"></i></span>`}
              </div>
              <div style="flex: 1; min-width: 0;">
                <p class="source-name" style="margin: 0 0 2px 0; font-size: 10px; font-weight: 800; text-transform: uppercase; color: var(--muted);">${escapeHtml(item.source)}</p>
                <h4 style="margin: 0 0 6px 0; font-size: 13px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${escapeHtml(item.title)}">${escapeHtml(item.title)}</h4>
                <div style="display: flex; align-items: center; gap: 6px; flex-wrap: wrap;">
                  ${badgesHtml}
                </div>
                ${suspiciousWarningHtml}
                ${unitPriceHtml}
              </div>
              <div style="text-align: right; flex-shrink: 0; display: flex; flex-direction: column; align-items: flex-end; gap: 6px;">
                <div>
                  ${originalPriceHtml}
                  ${priceDisplayHtml}
                </div>
                ${buttonHtml}
              </div>
            </div>
          `;
        }).join("")}
      </div>
      <div class="dialog-actions" style="margin-top: 0;">
        <button class="secondary-button" type="button" onclick="closeDialog()" style="width: 100%;">Vazgeç</button>
      </div>
    </div>
  `;

  state.searchResults = products;

  if (!dialog.open) dialog.showModal();
  lucide.createIcons();
}

window.triggerSuggestionSearch = function(query) {
  const input = document.getElementById("productUrl");
  if (input) {
    input.value = query;
    const form = document.getElementById("urlForm");
    if (form) {
      const submitBtn = form.querySelector("button[type='submit']");
      if (submitBtn) {
        submitBtn.click();
      } else {
        const event = new Event("submit", { cancelable: true });
        form.dispatchEvent(event);
      }
    }
  }
};


async function trackSearchResultProduct(button, index) {
  const item = state.searchResults ? state.searchResults[index] : null;
  if (!item) return;

  button.disabled = true;
  button.innerHTML = `<span class="spinner"></span> Ekleniyor`;

  try {
    await api("/products", {
      method: "POST",
      body: JSON.stringify({
        title: item.title,
        url: item.url,
        price: item.price,
        source: item.source,
        image_url: item.image_url,
        original_price: item.original_price,
        extra_info: item.extra_info || {}
      }),
    });

    showToast("Ürün radara eklendi.");
    closeDialog();
    document.getElementById("productUrl").value = "";
    await loadProducts();
    switchView("tracking");
  } catch (error) {
    showToast(`Ürün kaydedilemedi: ${error.message}`);
    button.disabled = false;
    button.innerHTML = `<i data-lucide="radar" style="width:12px; height:12px; margin-right:4px;"></i> Radara Ekle`;
    lucide.createIcons();
  }
}

function showParsedProduct(parsed) {
  state.parsedProduct = parsed;
  const dialog = document.getElementById("productDialog");
  const content = document.getElementById("dialogContent");
  const title = parsed.title || "Ürün bilgisi tamamlanamadı";

  const isSupplement = parsed.source === "supplementler" || 
                       parsed.source === "proteinocean" || 
                       (parsed.extra_info && parsed.extra_info.category === "supplement");

  const isCosmetics = parsed.source === "gratis" || 
                      parsed.source === "rossmann" || 
                      (parsed.extra_info && parsed.extra_info.category === "cosmetics");

  content.innerHTML = `
    <div class="dialog-product-image">
      ${parsed.image_url
        ? `<img src="${escapeHtml(proxiedImageUrl(parsed.image_url))}" alt="${escapeHtml(title)}"
            onerror="imageFallback(this, '${productFallbackIcons[parsed.source] || "package-search"}')">`
        : `<span class="product-placeholder"><i data-lucide="${productFallbackIcons[parsed.source] || "package-search"}"></i></span>`}
    </div>
    <div class="dialog-body">
      <p class="source-name">${escapeHtml(parsed.source)}</p>
      <h2>${escapeHtml(title)}</h2>
      <div class="decision-panel">
        <div class="score-ring">${parsed.confidence}</div>
        <div>
          <strong>Bilgi güveni</strong>
          <p>${parsed.price ? "Ürün ve fiyat bilgisi bulundu." : "Fiyat bulunamadı. Aşağıdan elle tamamlayabilirsin."}</p>
        </div>
      </div>
      <div class="manual-fields">
        <label class="manual-field">
          <span>Ürün adı</span>
          <input id="parsedTitle" type="text" value="${escapeHtml(parsed.title || "")}" placeholder="Ürün adını yaz">
        </label>
        <label class="manual-field">
          <span>Güncel fiyat</span>
          <input id="parsedPrice" type="text" inputmode="decimal" value="${parsed.price ?? ""}" placeholder="Örn. 1849,90">
        </label>
        <label class="manual-field">
          <span>Hedef Fiyat Eşiği (Alarm)</span>
          <input id="parsedTargetPrice" type="text" inputmode="decimal" placeholder="Bu fiyata düşünce haber ver (İsteğe bağlı)">
        </label>
        <label class="manual-field">
          <span>Fiyat Düşüş Alarmı (%)</span>
          <input id="parsedAlertThreshold" type="number" min="1" max="100" value="5">
        </label>
        <label class="manual-field">
          <span>Son Satın Alma Tarihi</span>
          <input id="parsedLastPurchasedDate" type="date">
        </label>
        <label class="manual-field">
          <span>Tekrar Alma Periyodu (Gün)</span>
          <input id="parsedRestockPeriod" type="number" min="1" max="730" placeholder="Örn. 30">
        </label>
        ${isSupplement ? `
        <label class="manual-field">
          <span>Toplam Servis Sayısı</span>
          <input id="parsedServings" type="number" value="${parsed.extra_info && parsed.extra_info.servings ? parsed.extra_info.servings : ""}" placeholder="Örn. 60">
        </label>
        <div id="parsedServingPriceRow" class="form-hint" style="margin-top: -6px; color: var(--green); font-weight: 700; min-height: 16px;"></div>
        ` : ""}
        ${isCosmetics ? `
        <label class="manual-field">
          <span>Kozmetik Açılış Tarihi</span>
          <input id="parsedOpeningDate" type="date" value="" placeholder="Açılış Tarihi">
        </label>
        <label class="manual-field">
          <span>Kullanım Ömrü (Ay)</span>
          <input id="parsedShelfLife" type="number" value="12" placeholder="Örn. 12">
        </label>
        ` : ""}
        <p class="form-hint">Otomatik bulunan bilgileri kontrol edip düzeltebilirsin.</p>
      </div>
      ${parsed.warnings.length ? `<p class="source-name">${parsed.warnings.map(escapeHtml).join(" ")}</p>` : ""}
      <p class="dialog-error" id="trackProductError" hidden></p>
      <div class="dialog-actions">
        <button class="secondary-button" type="button" onclick="closeDialog()">Vazgeç</button>
        <button class="primary-button" type="button" id="trackParsedButton" onclick="trackParsedProduct()">
          <i data-lucide="radar"></i>
          Takibe al
        </button>
      </div>
    </div>
  `;

  dialog.showModal();
  document.getElementById("parsedTitle").addEventListener("input", updateTrackButton);
  document.getElementById("parsedPrice").addEventListener("input", updateTrackButton);
  
  const updateServingPrice = () => {
    const servingsInput = document.getElementById("parsedServings");
    const priceInput = document.getElementById("parsedPrice");
    const display = document.getElementById("parsedServingPriceRow");
    if (!servingsInput || !priceInput || !display) return;

    const price = parseUserPrice(priceInput.value);
    const servings = parseInt(servingsInput.value, 10);

    if (price && servings && servings > 0) {
      const perServing = price / servings;
      display.textContent = `Servis başına maliyet: ${currency.format(perServing)}`;
    } else {
      display.textContent = "";
    }
  };

  if (isSupplement) {
    document.getElementById("parsedServings").addEventListener("input", updateServingPrice);
    document.getElementById("parsedPrice").addEventListener("input", updateServingPrice);
    updateServingPrice();
  }

  updateTrackButton();
  lucide.createIcons();
}

function parseUserPrice(value) {
  let text = String(value || "").trim().replace(/[^\d,.]/g, "");
  if (!text) return null;

  if (text.includes(",") && text.includes(".")) {
    text = text.lastIndexOf(",") > text.lastIndexOf(".")
      ? text.replaceAll(".", "").replace(",", ".")
      : text.replaceAll(",", "");
  } else if (text.includes(",")) {
    text = text.replaceAll(".", "").replace(",", ".");
  } else {
    const parts = text.split(".");
    if (parts.length === 2 && parts[1].length === 3) text = parts.join("");
  }

  const price = Number(text);
  return Number.isFinite(price) && price > 0 ? price : null;
}

function updateTrackButton() {
  const button = document.getElementById("trackParsedButton");
  if (!button) return;

  const title = document.getElementById("parsedTitle").value.trim();
  const price = parseUserPrice(document.getElementById("parsedPrice").value);
  button.disabled = !title || !price;
}

async function trackParsedProduct() {
  const parsed = state.parsedProduct;
  if (!parsed) return;

  const button = document.getElementById("trackParsedButton");
  const errorBox = document.getElementById("trackProductError");
  const title = document.getElementById("parsedTitle").value.trim();
  const price = parseUserPrice(document.getElementById("parsedPrice").value);

  const targetPriceInput = document.getElementById("parsedTargetPrice");
  const targetPrice = targetPriceInput ? parseUserPrice(targetPriceInput.value) : null;
  const alertThresholdInput = document.getElementById("parsedAlertThreshold");
  const alertThreshold = alertThresholdInput
    ? Number(alertThresholdInput.value)
    : 5;
  const lastPurchasedDate = document.getElementById("parsedLastPurchasedDate")?.value || "";
  const restockPeriod = Number(document.getElementById("parsedRestockPeriod")?.value || 0);

  const servingsInput = document.getElementById("parsedServings");
  const servings = servingsInput ? parseInt(servingsInput.value, 10) : null;

  if (!title || !price) {
    showDialogError("Ürün adı ve geçerli fiyat gerekli.");
    return;
  }

  button.disabled = true;
  button.innerHTML = `<span class="spinner"></span> Kaydediliyor`;
  errorBox.hidden = true;

  const extraInfo = { ...(parsed.extra_info || {}) };
  if (targetPrice) {
    extraInfo.target_price = targetPrice;
  }
  if (Number.isFinite(alertThreshold) && alertThreshold >= 1 && alertThreshold <= 100) {
    extraInfo.alert_threshold = alertThreshold;
  }
  if (lastPurchasedDate && Number.isFinite(restockPeriod) && restockPeriod > 0) {
    extraInfo.last_purchased_date = lastPurchasedDate;
    extraInfo.restock_period_days = restockPeriod;
  }
  if (servings && !isNaN(servings)) {
    extraInfo.servings = servings;
  }

  const openingDateInput = document.getElementById("parsedOpeningDate");
  const openingDate = openingDateInput ? openingDateInput.value.trim() : null;
  const shelfLifeInput = document.getElementById("parsedShelfLife");
  const shelfLife = shelfLifeInput ? parseInt(shelfLifeInput.value, 10) : null;

  if (openingDate) {
    extraInfo.opening_date = openingDate;
  }
  if (shelfLife && !isNaN(shelfLife)) {
    extraInfo.shelf_life_months = shelfLife;
  }

  try {
    await api("/products", {
      method: "POST",
      body: JSON.stringify({
        title,
        url: parsed.canonical_url,
        price,
        source: parsed.source,
        image_url: parsed.image_url,
        original_price: parsed.original_price,
        extra_info: extraInfo,
      }),
    });

    closeDialog();
    document.getElementById("productUrl").value = "";
    showToast("Ürün fiyat radarına eklendi.");
    await loadProducts();
    switchView("tracking");
  } catch (error) {
    showDialogError(`Ürün kaydedilemedi: ${error.message}`);
    button.disabled = false;
    button.innerHTML = `<i data-lucide="radar"></i> Takibe al`;
    lucide.createIcons();
  }
}

function showDialogError(message) {
  const errorBox = document.getElementById("trackProductError");
  if (!errorBox) {
    showToast(message);
    return;
  }

  errorBox.textContent = message;
  errorBox.hidden = false;
  errorBox.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function openProduct(id) {
  const product = state.products.find((item) => item.id === id);
  if (!product) return;

  const dialog = document.getElementById("productDialog");
  const content = document.getElementById("dialogContent");
  const history = product.price_history.map((item) => item.price);
  const lowest = Math.min(...history);
  const highest = Math.max(...history);

  // Fiyat geçmişini kronolojik sıraya göre diz
  const sortedHistory = [...product.price_history].sort((a, b) => new Date(a.seen_at) - new Date(b.seen_at));
  const labels = sortedHistory.map((item) => {
    if (!item.seen_at) return "İlk Kayıt";
    return new Intl.DateTimeFormat("tr-TR", {
      day: "2-digit",
      month: "short",
    }).format(new Date(item.seen_at));
  });
  const prices = sortedHistory.map((item) => item.price);

  const extraInfo = product.extra_info || {};
  let assistantHtml = "";

  // 1. Supplement porsiyon ve servis maliyeti
  if (extraInfo.servings) {
    const servings = parseInt(extraInfo.servings, 10);
    const costPerServing = product.current_price / servings;
    assistantHtml += `
      <div class="assistant-info-box">
        <div class="assistant-info-title">
          <i data-lucide="dumbbell"></i> Porsiyon Analizi
        </div>
        <div class="assistant-info-content">
          Bu ürün <strong>${servings} servis</strong> içeriyor.<br>
          Servis başına maliyet: <strong>${currency.format(costPerServing)}</strong>
        </div>
      </div>
    `;
  }

  // 2. PC donanım uyumluluk bilgileri
  if (extraInfo.compatibility_info) {
    assistantHtml += `
      <div class="assistant-info-box">
        <div class="assistant-info-title">
          <i data-lucide="cpu"></i> Donanım Uyumluluk Rehberi
        </div>
        <div class="assistant-info-content">
          ${escapeHtml(extraInfo.compatibility_info)}
        </div>
      </div>
    `;
  }

  // 2.5. Kozmetik son kullanma ve ömür bilgisi
  if (extraInfo.opening_date && extraInfo.shelf_life_months) {
    const openingDate = new Date(extraInfo.opening_date);
    const shelfMonths = parseInt(extraInfo.shelf_life_months, 10);
    const expDate = new Date(openingDate.getTime() + shelfMonths * 30 * 24 * 60 * 60 * 1000);
    const now = new Date();
    const daysLeft = Math.ceil((expDate - now) / (1000 * 60 * 60 * 24));
    
    let statusMsg = "";
    if (daysLeft < 0) {
      statusMsg = `<span style="color: var(--red); font-weight: 700;">Kullanım ömrü dolmuş! (${Math.abs(daysLeft)} gün önce)</span>`;
    } else {
      statusMsg = `Kalan kullanım süresi: <strong>${daysLeft} gün</strong>`;
    }

    assistantHtml += `
      <div class="assistant-info-box">
        <div class="assistant-info-title">
          <i data-lucide="calendar"></i> Kozmetik Ömür Takibi
        </div>
        <div class="assistant-info-content">
          Açılış Tarihi: <strong>${extraInfo.opening_date}</strong> (Kullanım Ömrü: <strong>${shelfMonths} Ay</strong>)<br>
          Son Kullanma Hedefi: <strong>${expDate.toISOString().split('T')[0]}</strong><br>
          ${statusMsg}
        </div>
      </div>
    `;
  }

  if (extraInfo.last_purchased_date && extraInfo.restock_period_days) {
    const purchasedAt = new Date(extraInfo.last_purchased_date);
    const dueAt = new Date(
      purchasedAt.getTime()
      + Number(extraInfo.restock_period_days) * 24 * 60 * 60 * 1000,
    );
    const daysUntilDue = Math.ceil((dueAt - new Date()) / (24 * 60 * 60 * 1000));
    const restockStatus = daysUntilDue > 0
      ? `${daysUntilDue} gün sonra yeniden alma zamanı`
      : `${Math.abs(daysUntilDue)} gündür yeniden alma zamanı gelmiş`;

    assistantHtml += `
      <div class="assistant-info-box">
        <div class="assistant-info-title">
          <i data-lucide="repeat-2"></i> Periyodik İhtiyaç Asistanı
        </div>
        <div class="assistant-info-content">
          ${Number(extraInfo.restock_period_days)} günlük periyot takip ediliyor.<br>
          Sonraki hedef: <strong>${dueAt.toLocaleDateString("tr-TR")}</strong><br>
          <strong>${restockStatus}</strong>
        </div>
      </div>
    `;
  }

  // 3. Hedef fiyat alarm bilgisi
  if (extraInfo.target_price) {
    assistantHtml += `
      <div class="assistant-info-box">
        <div class="assistant-info-title">
          <i data-lucide="bell-ring"></i> Hedef Fiyat Alarmı
        </div>
        <div class="assistant-info-content">
          Hedef fiyatın: <strong>${currency.format(extraInfo.target_price)}</strong>. Fiyat bu seviyeye veya altına düştüğünde bildirim gönderilecektir.
        </div>
      </div>
    `;
  }

  // 4. Sahte İndirim Analiz Raporu
  const forecast = product.discount_forecast;
  if (forecast) {
    assistantHtml += `
      <div class="forecast-panel ${forecast.status === "ready" ? "" : "forecast-pending"}">
        <div class="forecast-heading">
          <div>
            <span class="forecast-label">7 GÜNLÜK TAHMİN</span>
            <strong>${forecast.status === "ready"
              ? `%${forecast.probability} indirim ihtimali`
              : "Tahmin hazırlanıyor"}</strong>
          </div>
          <span class="forecast-recommendation">${escapeHtml(forecast.recommendation)}</span>
        </div>
        <p>${escapeHtml(forecast.message)}</p>
        ${forecast.status === "ready" ? `
          <div class="forecast-stats">
            <span>Güven <strong>${escapeHtml(forecast.confidence)}</strong></span>
            <span>Beklenen düşüş <strong>%${forecast.expected_drop_percent}</strong></span>
            <span>Veri <strong>${forecast.observation_count} kayıt</strong></span>
          </div>
        ` : ""}
      </div>
    `;
  }

  const discountAnalysis = product.discount_analysis;
  if (discountAnalysis) {
    const badgeColor = discountAnalysis.badge_color || "gray";
    const statusText = discountAnalysis.status || "normal";
    assistantHtml += `
      <div class="discount-analysis-panel badge-${badgeColor}">
        <span class="analysis-status-badge bg-${badgeColor}">${escapeHtml(statusText)}</span>
        <div class="assistant-info-content" style="font-weight: 500;">
          ${escapeHtml(discountAnalysis.message)}
        </div>
      </div>
    `;
  }

  // 5. Diğer Mağaza Fiyat Karşılaştırması
  const comparison = product.price_comparison || [];
  let comparisonHtml = "";
  if (comparison.length > 0) {
    comparisonHtml += `
      <div class="price-chart-container" style="margin: 18px 0; padding: 12px; background: #f4f6f2; border: 1px solid var(--line); border-radius: 8px;">
        <p class="source-name" style="margin-top: 0; margin-bottom: 10px; font-weight: 700; color: var(--green-dark); display: flex; align-items: center; justify-content: space-between;">
          <span style="display: flex; align-items: center; gap: 6px;"><i data-lucide="arrow-left-right" style="width: 14px; height: 14px;"></i> Diğer Mağazalardaki Fiyatlar</span>
          <button onclick="refreshProductComparison('${product.id}')" style="background: none; border: none; color: var(--green); font-size: 11px; font-weight: 700; cursor: pointer; padding: 0; display: flex; align-items: center; gap: 4px;">
            <i data-lucide="refresh-cw" style="width: 11px; height: 11px;"></i> Yenile
          </button>
        </p>
        <div style="display: flex; flex-direction: column; gap: 8px;">
          ${comparison.map((item, idx) => {
            const isCheapest = idx === 0 && item.price < product.current_price;
            const borderStyle = isCheapest ? "border: 1px solid var(--green); background: #eaf6ec;" : "border: 1px solid var(--line); background: white;";
            const badgeStyle = isCheapest ? "background: var(--green); color: white; padding: 2px 4px; border-radius: 4px; font-size: 9px; font-weight: 800; margin-left: 4px;" : "";
            return `
            <div style="display: flex; align-items: center; justify-content: space-between; padding: 8px 10px; border-radius: 6px; ${borderStyle}">
              <div style="display: flex; align-items: center; gap: 8px; min-width: 0; flex: 1; margin-right: 10px;">
                <span style="font-size: 11px; font-weight: 800; text-transform: uppercase; color: var(--muted); min-width: 75px; display: inline-block;">${escapeHtml(item.store)}</span>
                <span style="font-size: 12px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--ink);">${escapeHtml(item.title)}</span>
              </div>
              <div style="display: flex; align-items: center; gap: 10px; flex-shrink: 0;">
                <strong style="color: ${isCheapest ? "var(--green-dark)" : "var(--ink)"}; font-size: 13px;">${currency.format(item.price)}</strong>
                ${isCheapest ? `<span style="${badgeStyle}">EN UCUZ</span>` : ""}
                <a href="${escapeHtml(item.url)}" target="_blank" style="color: var(--muted); display: inline-grid; place-items: center; width: 26px; height: 26px; border: 1px solid var(--line); border-radius: 4px; background: white;" title="Mağazaya git">
                  <i data-lucide="external-link" style="width: 14px; height: 14px; color: var(--ink);"></i>
                </a>
              </div>
            </div>
            `;
          }).join("")}
        </div>
      </div>
    `;
  } else {
    comparisonHtml += `
      <div class="price-chart-container" style="margin: 18px 0; padding: 12px; background: #fbfcf9; border: 1px solid var(--line); border-radius: 6px; text-align: center;">
        <button class="card-button" style="margin-top: 0; width: auto; display: inline-flex; align-items: center; gap: 6px; padding: 8px 16px;" onclick="refreshProductComparison('${product.id}')">
          <i data-lucide="search" style="width: 14px; height: 14px;"></i>
          Diğer Mağazalardaki Fiyatları Sorgula
        </button>
      </div>
    `;
  }

  content.innerHTML = `
    <div class="dialog-product-image">${productImage(product)}</div>
    <div class="dialog-body">
      <p class="source-name">${escapeHtml(product.source)}</p>
      <h2>${escapeHtml(product.title)}</h2>
      <div class="decision-panel">
        <div class="score-ring">${product.deal_score}</div>
        <div>
          <strong>${escapeHtml(product.verdict.toUpperCase())}</strong>
          <p>${escapeHtml(product.reason)}</p>
        </div>
      </div>
      
      <!-- Akıllı Asistan Bilgileri -->
      ${assistantHtml}

      <div class="price-row">
        <span class="price">${currency.format(product.current_price)}</span>
        <span class="verdict">${escapeHtml(product.verdict)}</span>
      </div>
      <p class="source-name">En düşük ${currency.format(lowest)} · En yüksek ${currency.format(highest)}</p>
      
      <!-- Fiyat Geçmişi Grafiği -->
      <div class="price-chart-container" style="margin: 18px 0; padding: 12px; background: #fbfcf9; border: 1px solid var(--line); border-radius: 6px;">
        <p class="source-name" style="margin-top: 0; margin-bottom: 8px; font-weight: 600; color: var(--ink);">Fiyat Değişim Grafiği</p>
        <div style="position: relative; height: 160px; width: 100%;">
          <canvas id="priceHistoryChart"></canvas>
        </div>
      </div>

      <!-- Fiyat Karşılaştırması -->
      ${comparisonHtml}

      <div class="manual-fields">
        <label class="manual-field">
          <span>Yeni fiyat kaydı</span>
          <input id="newPriceInput" type="text" inputmode="decimal" placeholder="Örn. 1749,90">
        </label>
        <button class="secondary-button" onclick="updateProductPrice('${product.id}')">Fiyatı güncelle</button>
      </div>
      <div class="dialog-actions">
        <button class="danger-button" type="button" onclick="removeTrackedProduct('${product.id}')">
          <i data-lucide="trash-2"></i>
          Takipten çıkar
        </button>
        <button class="primary-button" onclick="window.open('${escapeHtml(product.url)}', '_blank')">
          <i data-lucide="external-link"></i>
          Mağazaya git
        </button>
      </div>
      <button class="card-button" onclick="refreshSingleProduct('${product.id}')">
        <i data-lucide="refresh-cw"></i>
        Şimdi otomatik kontrol et
      </button>
    </div>
  `;

  dialog.showModal();
  lucide.createIcons();

  // Grafik çizimi
  setTimeout(() => {
    const ctx = document.getElementById("priceHistoryChart");
    if (!ctx) return;

    const existingChart = Chart.getChart(ctx);
    if (existingChart) {
      existingChart.destroy();
    }

    new Chart(ctx, {
      type: "line",
      data: {
        labels: labels,
        datasets: [
          {
            label: "Fiyat",
            data: prices,
            borderColor: "#287a50", // --green
            backgroundColor: "rgba(40, 122, 80, 0.08)",
            borderWidth: 2,
            tension: 0.15,
            pointBackgroundColor: "#287a50",
            pointBorderColor: "#ffffff",
            pointBorderWidth: 1.5,
            pointRadius: 4.5,
            pointHoverRadius: 6.5,
            fill: true,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            mode: "index",
            intersect: false,
            callbacks: {
              label: function (context) {
                return currency.format(context.raw);
              },
            },
          },
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: {
              font: { family: "DM Sans", size: 10 },
              color: "#687068",
            },
          },
          y: {
            grid: { color: "#dfe3dc" },
            ticks: {
              font: { family: "DM Sans", size: 10 },
              color: "#687068",
              callback: function (value) {
                return "₺" + value;
              },
            },
          },
        },
      },
    });
  }, 100);
}

async function updateProductPrice(productId) {
  const input = document.getElementById("newPriceInput");
  const price = parseUserPrice(input?.value);

  if (!price) {
    showToast("Geçerli bir fiyat yaz.");
    return;
  }

  try {
    const updated = await api(`/products/${productId}/prices`, {
      method: "POST",
      body: JSON.stringify({ price }),
    });

    state.products = state.products.map((product) => (
      product.id === productId ? updated : product
    ));
    renderAll();
    showToast("Yeni fiyat kaydedildi, fırsat skoru güncellendi.");
    openProduct(productId);
  } catch (error) {
    showToast(error.message);
  }
}

async function removeTrackedProduct(productId) {
  const product = state.products.find((item) => item.id === productId);
  if (!product) return;

  const confirmed = window.confirm(`"${product.title}" takipten çıkarılsın mı?`);
  if (!confirmed) return;

  try {
    await api(`/products/${productId}`, { method: "DELETE" });
    state.products = state.products.filter((item) => item.id !== productId);
    closeDialog();
    renderAll();
    showToast("Ürün takip listesinden çıkarıldı.");
  } catch (error) {
    showToast(error.message);
  }
}

async function refreshSingleProduct(productId) {
  showToast("Ürünün güncel fiyatı kontrol ediliyor...");

  try {
    const result = await api(`/products/${productId}/refresh`, {
      method: "POST",
    });

    state.products = state.products.map((product) => (
      product.id === productId ? result.product : product
    ));
    renderAll();
    openProduct(productId);

    if (result.status === "success" && result.price_changed) {
      showToast(`Fiyat güncellendi: ${currency.format(result.new_price)}`);
    } else if (result.status === "success") {
      showToast("Fiyat değişmemiş.");
    } else {
      showToast(`Fiyat bulunamadı: ${result.message}`);
    }
  } catch (error) {
    showToast(error.message);
  }
}

async function refreshAllPrices() {
  const button = document.getElementById("refreshButton");
  button.disabled = true;
  button.innerHTML = `<span class="spinner"></span> Kontrol ediliyor`;

  try {
    const result = await api("/refresh-all", { method: "POST" });
    await loadProducts();
    showToast(`${result.successful} ürün kontrol edildi, ${result.failed} üründe fiyat bulunamadı.`);
  } catch (error) {
    showToast(error.message);
  } finally {
    button.disabled = false;
    button.innerHTML = `<i data-lucide="scan-line"></i> Fiyatları kontrol et`;
    lucide.createIcons();
  }
}

async function showNotifications() {
  try {
    const [notifications, pushConfig] = await Promise.all([
      api("/notifications"),
      api("/push/config"),
    ]);
    const dialog = document.getElementById("productDialog");
    const content = document.getElementById("dialogContent");
    const pushState = await currentPushState(pushConfig);

    content.innerHTML = `
      <div class="dialog-body">
        <p class="eyebrow">BİLDİRİMLER</p>
        <h2>Fırsat hareketleri</h2>
        <div class="push-settings">
          <div>
            <strong>Fiyat alarmı bildirimleri</strong>
            <span>${escapeHtml(pushState.message)}</span>
          </div>
          ${pushState.action === "enable"
            ? `<button class="primary-button compact-button" type="button" onclick="enablePushNotifications()">Aç</button>`
            : pushState.action === "disable"
              ? `<button class="secondary-button compact-button" type="button" onclick="disablePushNotifications()">Kapat</button>`
              : ""}
        </div>
        <div class="notification-list">
          ${notifications.length
            ? notifications.map((item) => {
                let badgeHtml = "";
                if (item.type === "catalog_bim") {
                  badgeHtml = `<span class="analysis-status-badge bg-blue" style="font-size: 9px; padding: 2px 4px; border-radius: 3px; font-weight: 700; margin-right: 6px;">BİM AKTÜEL</span>`;
                } else if (item.type === "catalog_a101") {
                  badgeHtml = `<span class="analysis-status-badge bg-yellow" style="font-size: 9px; padding: 2px 4px; border-radius: 3px; font-weight: 700; color: #775815; margin-right: 6px;">A101 AKTÜEL</span>`;
                } else if (item.type === "catalog_gratis") {
                  badgeHtml = `<span class="analysis-status-badge bg-red" style="font-size: 9px; padding: 2px 4px; border-radius: 3px; font-weight: 700; margin-right: 6px;">GRATİS</span>`;
                } else if (item.type === "stock_back") {
                  badgeHtml = `<span class="analysis-status-badge bg-green" style="font-size: 9px; padding: 2px 4px; border-radius: 3px; font-weight: 700; margin-right: 6px;">STOK GELDİ</span>`;
                } else if (item.type === "catalog_match") {
                  badgeHtml = `<span class="analysis-status-badge bg-green" style="font-size: 9px; padding: 2px 4px; border-radius: 3px; font-weight: 700; margin-right: 6px;">KATALOĞA DÜŞTÜ!</span>`;
                }
                
                return `
                  <div class="notification-item">
                    <div style="display: flex; align-items: center; margin-bottom: 4px;">
                      ${badgeHtml}
                      <strong>${escapeHtml(item.title)}</strong>
                    </div>
                    <span>${escapeHtml(item.message)}</span>
                    <time>${formatDate(item.created_at)}</time>
                  </div>
                `;
              }).join("")
            : `<div class="empty-state">Henüz fiyat düşüşü bildirimi yok.</div>`}
        </div>
      </div>
    `;
    dialog.showModal();
    await api("/notifications/read-all", { method: "POST" });
  } catch (error) {
    showToast(error.message);
  }
}

async function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) return null;
  try {
    return await navigator.serviceWorker.register("/sw.js");
  } catch {
    return null;
  }
}

async function currentPushState(config) {
  if (!config.enabled) {
    return {
      action: null,
      message: "Sunucuda web bildirimleri henüz etkin değil.",
    };
  }
  if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
    return {
      action: null,
      message: "Bu tarayıcı web bildirimlerini desteklemiyor.",
    };
  }
  if (Notification.permission === "denied") {
    return {
      action: null,
      message: "Bildirim izni tarayıcı ayarlarından engellenmiş.",
    };
  }

  const registration = await navigator.serviceWorker.ready;
  const subscription = await registration.pushManager.getSubscription();
  return subscription
    ? { action: "disable", message: "Bu cihazda bildirimler açık." }
    : { action: "enable", message: "Hedef fiyat ve ciddi düşüşlerde haber al." };
}

function urlBase64ToUint8Array(value) {
  const padding = "=".repeat((4 - (value.length % 4)) % 4);
  const base64 = (value + padding).replaceAll("-", "+").replaceAll("_", "/");
  const raw = atob(base64);
  return Uint8Array.from([...raw].map((character) => character.charCodeAt(0)));
}

async function enablePushNotifications() {
  try {
    const config = await api("/push/config");
    if (!config.enabled || !config.public_key) {
      throw new Error("Web bildirimleri sunucuda henüz etkinleştirilmedi.");
    }

    const permission = await Notification.requestPermission();
    if (permission !== "granted") {
      throw new Error("Bildirim izni verilmedi.");
    }

    const registration = await navigator.serviceWorker.ready;
    let subscription = await registration.pushManager.getSubscription();
    if (!subscription) {
      subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(config.public_key),
      });
    }

    await api("/push/subscriptions", {
      method: "POST",
      body: JSON.stringify(subscription.toJSON()),
    });
    closeDialog();
    showToast("Fiyat alarmı bildirimleri açıldı.");
  } catch (error) {
    showToast(error.message);
  }
}

async function disablePushNotifications() {
  try {
    const registration = await navigator.serviceWorker.ready;
    const subscription = await registration.pushManager.getSubscription();
    if (subscription) {
      await api("/push/subscriptions", {
        method: "DELETE",
        body: JSON.stringify(subscription.toJSON()),
      });
      await subscription.unsubscribe();
    }
    closeDialog();
    showToast("Bu cihazdaki bildirimler kapatıldı.");
  } catch (error) {
    showToast(error.message);
  }
}

function checkStatusText(product) {
  if (product.last_check_status === "success") {
    return `Son kontrol: ${formatDate(product.last_checked_at)}`;
  }
  if (product.last_check_status === "failed") {
    return "Otomatik fiyat bulunamadı";
  }
  return "İlk otomatik kontrol bekleniyor";
}

function formatDate(value) {
  if (!value) return "Henüz kontrol edilmedi";
  return new Intl.DateTimeFormat("tr-TR", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function productImage(product) {
  if (product.image_url) {
    return `<img src="${escapeHtml(proxiedImageUrl(product.image_url))}" alt="${escapeHtml(product.title)}"
      loading="lazy" onerror="imageFallback(this, '${productFallbackIcons[product.source] || "package-search"}')">`;
  }
  const icon = productFallbackIcons[product.source] || "package-search";
  return `<span class="product-placeholder"><i data-lucide="${icon}"></i></span>`;
}

function switchView(view) {
  state.activeView = view;
  const sections = {
    discover: document.getElementById("discoverView"),
    tracking: document.getElementById("trackingView"),
    savings: document.getElementById("savingsView"),
    cart: document.getElementById("cartView"),
  };

  Object.entries(sections).forEach(([name, section]) => {
    if (section) section.classList.toggle("hidden", name !== view);
  });

  document.querySelectorAll("[data-view]").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === view);
  });

  if (view === "cart") {
    renderCart();
  }

  window.scrollTo({ top: view === "discover" ? 0 : 180, behavior: "smooth" });
}

async function pasteUrl() {
  try {
    const value = await navigator.clipboard.readText();
    document.getElementById("productUrl").value = value;
  } catch {
    showToast("Pano izni verilmedi. Linki elle yapıştırabilirsin.");
  }
}

async function refreshProductComparison(productId) {
  showToast("Diğer mağazalardaki fiyatlar sorgulanıyor...");
  try {
    const updated = await api(`/products/${productId}/compare`, {
      method: "POST",
    });

    state.products = state.products.map((product) => (
      product.id === productId ? updated : product
    ));
    renderAll();
    openProduct(productId);
    showToast("Diğer mağaza fiyatları güncellendi.");
  } catch (error) {
    showToast(error.message);
  }
}

function closeDialog() {
  const dialog = document.getElementById("productDialog");
  if (dialog.open) dialog.close();
}

function showToast(message) {
  const toast = document.getElementById("toast");
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(showToast.timeout);
  showToast.timeout = setTimeout(() => toast.classList.remove("show"), 2800);
}

function updateNetworkStatus() {
  const status = document.getElementById("networkStatus");
  if (!status) return;
  const online = navigator.onLine;
  status.classList.toggle("offline", !online);
  status.innerHTML = online
    ? `<i data-lucide="wifi"></i><span>Çevrimiçi</span>`
    : `<i data-lucide="wifi-off"></i><span>Çevrimdışı mod</span>`;
  lucide.createIcons();
  if (!online) {
    showToast("Çevrimdışı mod aktif. Kayıtlı liste ve market karşılaştırmaları kullanılabilir.");
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function getOrCreateDeviceId() {
  const storageKey = "almadan_device_id";
  let deviceId = localStorage.getItem(storageKey);

  if (!deviceId) {
    deviceId = globalThis.crypto?.randomUUID
      ? globalThis.crypto.randomUUID()
      : `device-${Date.now()}-${Math.random().toString(16).slice(2)}`;
    localStorage.setItem(storageKey, deviceId);
  }

  return deviceId;
}

function togglePhoneField() {
  const pref = document.getElementById("authNotificationPref")?.value;
  const phoneField = document.getElementById("phoneFieldLabel");
  if (phoneField) {
    phoneField.style.display = pref === "email" ? "none" : "block";
  }
}

window.openProduct = openProduct;
window.closeDialog = closeDialog;
window.trackParsedProduct = trackParsedProduct;
window.updateProductPrice = updateProductPrice;
window.refreshSingleProduct = refreshSingleProduct;
window.removeTrackedProduct = removeTrackedProduct;
window.refreshProductComparison = refreshProductComparison;
window.submitAuth = submitAuth;
window.logoutAccount = logoutAccount;
window.showAccount = showAccount;
window.showForgotPassword = showForgotPassword;
window.sendPasswordReset = sendPasswordReset;
window.submitPasswordReset = submitPasswordReset;
window.enablePushNotifications = enablePushNotifications;
window.disablePushNotifications = disablePushNotifications;
window.trackSearchResultProduct = trackSearchResultProduct;
window.togglePhoneField = togglePhoneField;
window.toggleProfilePhoneField = toggleProfilePhoneField;
window.saveProfileSettings = saveProfileSettings;

// NEW FUNCTIONS EXPORTS
window.toggleTheme = toggleTheme;
window.addQuickCartItem = addQuickCartItem;
window.clearCart = clearCart;
window.toggleCartItem = toggleCartItem;
window.removeCartItem = removeCartItem;
window.shareCartList = shareCartList;
window.toggleScannerArea = toggleScannerArea;
window.runBarcodeScan = runBarcodeScan;
window.runOcrScan = runOcrScan;
window.switchOptimizerMode = switchOptimizerMode;
window.startVoiceSearch = startVoiceSearch;


/* PREMIUM KOYU TEMA */
function applyTheme() {
  const isDark = state.theme === "dark";
  document.documentElement.classList.toggle("dark-theme", isDark);
  document.body.classList.toggle("dark-theme", isDark);
  const themeBtn = document.getElementById("themeToggleButton");
  if (themeBtn) {
    themeBtn.innerHTML = isDark ? `<i data-lucide="sun"></i>` : `<i data-lucide="moon"></i>`;
    lucide.createIcons();
  }
}

function toggleTheme() {
  state.theme = state.theme === "light" ? "dark" : "light";
  localStorage.setItem("almadan_theme", state.theme);
  applyTheme();
  renderSavingsCharts();
}


/* SEPETİM & ALIVERİŞ LİSTEM */
function addQuickCartItem() {
  const input = document.getElementById("quickCartInput");
  const val = input.value.trim();
  if (!val) return;

  const newItem = {
    id: "cart-" + Date.now(),
    name: val,
    checked: false,
    updated_at: new Date().toISOString(),
  };

  state.cart.push(newItem);
  saveCartToLocalStorage();
  input.value = "";
  renderCart();
  
  if (state.sharedListId) {
    syncSharedListWithServer();
  }
}

function clearCart() {
  if (state.cart.length === 0) return;
  const confirmed = window.confirm("Tüm sepeti temizlemek istediğinizden emin misiniz?");
  if (!confirmed) return;

  state.cart = [];
  saveCartToLocalStorage();
  renderCart();

  if (state.sharedListId) {
    syncSharedListWithServer();
  }
}

function toggleCartItem(itemId) {
  state.cart = state.cart.map(item => {
    if (item.id === itemId) {
      return {
        ...item,
        checked: !item.checked,
        updated_at: new Date().toISOString(),
      };
    }
    return item;
  });
  saveCartToLocalStorage();
  renderCart();

  if (state.sharedListId) {
    syncSharedListWithServer();
  }
}

function removeCartItem(itemId) {
  state.cart = state.cart.filter(item => item.id !== itemId);
  saveCartToLocalStorage();
  renderCart();

  if (state.sharedListId) {
    syncSharedListWithServer();
  }
}

function updateCartQuantity(itemId, value) {
  const quantity = Math.max(1, Math.min(99, Number.parseInt(value, 10) || 1));
  state.cart = state.cart.map(item => (
    item.id === itemId
      ? { ...item, quantity, updated_at: new Date().toISOString() }
      : item
  ));
  saveCartToLocalStorage();
  renderCart();
  if (state.sharedListId) syncSharedListWithServer();
}

function saveCartToLocalStorage() {
  localStorage.setItem("almadan_cart", JSON.stringify(state.cart));
}


/* SCANNERS AND OCR SIMULATION */
function toggleScannerArea(type) {
  const area = document.getElementById("barcodeOcrInputArea");
  const barcode = document.getElementById("barcodeScannerArea");
  const ocr = document.getElementById("receiptOcrUploadArea");

  if (type === "barcode") {
    const isHidden = barcode.classList.contains("hidden");
    area.classList.toggle("hidden", !isHidden);
    barcode.classList.toggle("hidden", !isHidden);
    ocr.classList.add("hidden");
  } else {
    const isHidden = ocr.classList.contains("hidden");
    area.classList.toggle("hidden", !isHidden);
    ocr.classList.toggle("hidden", !isHidden);
    barcode.classList.add("hidden");
  }
}

async function runBarcodeScan() {
  const code = document.getElementById("barcodeSelector").value;
  if (!code) {
    showToast("Lütfen bir barkod seçin.");
    return;
  }

  await lookupAndAddBarcode(code);
}

async function lookupAndAddBarcode(code) {
  showToast("Barkod taranıyor...");
  try {
    const res = await api(`/api/barcode/${code}`);
    if (res.found) {
      const newItem = {
        id: "cart-" + Date.now(),
        name: res.title,
        checked: false,
        updated_at: new Date().toISOString(),
      };
      state.cart.push(newItem);
      saveCartToLocalStorage();
      renderCart();
      showToast(`Barkod bulundu ve eklendi: ${res.title}`);
      
      if (state.sharedListId) {
        syncSharedListWithServer();
      }
    } else {
      showToast(res.message);
    }
  } catch (error) {
    showToast(error.message);
  }
}

async function scanBarcodeImage(event) {
  const file = event.target.files?.[0];
  if (!file) return;

  if (!("BarcodeDetector" in window)) {
    showToast("Bu tarayıcı fotoğraftan barkod okumayı desteklemiyor. Demo barkod listesini kullanabilirsin.");
    return;
  }

  try {
    const detector = new BarcodeDetector({
      formats: ["ean_13", "ean_8", "upc_a", "upc_e"],
    });
    const bitmap = await createImageBitmap(file);
    const barcodes = await detector.detect(bitmap);
    bitmap.close();

    if (!barcodes.length) {
      showToast("Fotoğrafta okunabilir EAN barkodu bulunamadı.");
      return;
    }
    await lookupAndAddBarcode(barcodes[0].rawValue);
  } catch (error) {
    showToast(`Barkod okunamadı: ${error.message}`);
  } finally {
    event.target.value = "";
  }
}

function previewReceiptFile(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  const info = document.querySelector("#receiptOcrUploadArea .ocr-info");
  if (info) info.textContent = `${file.name} seçildi. OCR taramasını başlatabilirsin.`;
}

async function runOcrScan() {
  const cat = document.getElementById("ocrReceiptCategorySelector").value || "grocery";
  const receiptFile = document.getElementById("receiptImageInput")?.files?.[0];
  showToast("Fiş fotoğrafı işleniyor (OCR)...");
  try {
    const res = await api("/api/ocr/receipt", {
      method: "POST",
      body: JSON.stringify({
        image_base64: receiptFile ? `${cat}:${receiptFile.name}` : cat,
      })
    });
    
    if (res.detected_items && res.detected_items.length > 0) {
      const summary = res.detected_items
        .map(item => `${item.title} - ${currency.format(item.price)}`)
        .join("\n");
      const confirmed = window.confirm(
        `${res.store.toUpperCase()} fişinde şu ürünler bulundu:\n\n${summary}\n\nListeye eklensin mi?`
      );
      if (!confirmed) {
        showToast("Fiş ürünleri listeye eklenmedi.");
        return;
      }
      res.detected_items.forEach((item, index) => {
        state.cart.push({
          id: "cart-" + Date.now() + "-" + index,
          name: item.title,
          checked: false,
          receipt_price: item.price,
          updated_at: new Date().toISOString(),
        });
      });
      saveCartToLocalStorage();
      renderCart();
      showToast(`OCR Başarılı! ${res.detected_items.length} ürün listenize eklendi.`);
      
      if (state.sharedListId) {
        syncSharedListWithServer();
      }
      const receiptInput = document.getElementById("receiptImageInput");
      if (receiptInput) receiptInput.value = "";
    }
  } catch (error) {
    showToast(error.message);
  }
}


/* SEPET EN İYİLEŞTİRİCİ MOTORU */
function switchOptimizerMode(mode) {
  state.optimizerMode = mode;
  document.getElementById("optModeSingle").classList.toggle("active", mode === "single");
  document.getElementById("optModeSplit").classList.toggle("active", mode === "split");
  renderCart();
}

function getItemCategory(name) {
  const lower = name.toLowerCase();
  const groceryKeywords = ["yağ", "yag", "seker", "şeker", "un", "bakliyat", "makarna", "pirinc", "pirinç", "mercimek", "salca", "salça", "cay", "çay", "kahve", "sut", "süt", "peynir", "zeytin", "yumurta", "deterjan", "sabun", "bulaşık", "çamaşır", "domates", "soğan", "patates", "ekmek", "yoğurt", "yogurt", "makarna", "salata", "su", "kola"];
  const electronicsKeywords = ["tv", "televizyon", "telefon", "kulaklik", "kulaklık", "laptop", "bilgisayar", "ekran", "kart", "gpu", "cpu", "islemci", "işlemci", "anakart", "ram", "ssd", "klavye", "mouse", "fare", "tablet", "kamera", "fotoğraf", "monitör", "monitor", "disk", "sabit disk", "bellek"];
  const fashionKeywords = ["elbise", "pantolon", "gomlek", "gömlek", "tshirt", "tişört", "ceket", "mont", "kaban", "hırka", "hirka", "kazak", "yelek", "ayakkabi", "ayakkabı", "bot", "çizme", "terlik", "corap", "çorap", "etek", "sort", "şort", "takim", "takım", "bluz", "sweatshirt", "sweat", "kemer", "cüzdan", "aksesuar"];
  const supplementKeywords = ["whey", "protein", "creatine", "kreatin", "gainer", "bcaa", "arginine", "arjinin", "supplement", "takviye", "karbonhidrat", "glutamine", "glutamin", "aminoasit", "preworkout", "vitamin", "kolajen", "collagen"];
  const cosmeticsKeywords = ["şampuan", "sampuan", "krem", "parfüm", "parfum", "ruj", "maskara", "fondöten", "oje", "far", "allık", "liner", "eyeliner", "saç kremi", "saç boyası", "tonik", "serum", "nemlendirici", "losyon", "gratis", "rossmann", "deodorant", "roll-on", "diş macunu", "dis macunu", "diş fırçası", "makyaj"];
  
  if (supplementKeywords.some(kw => lower.includes(kw))) return "supplement";
  if (electronicsKeywords.some(kw => lower.includes(kw))) return "electronics";
  if (cosmeticsKeywords.some(kw => lower.includes(kw))) return "cosmetics";
  if (fashionKeywords.some(kw => lower.includes(kw))) return "fashion";
  if (groceryKeywords.some(kw => lower.includes(kw))) return "grocery";
  
  return "grocery";
}

const CATEGORY_STORES = {
  grocery: ["bim", "a101", "sok", "file", "metro", "carrefoursa", "migros", "trendyol", "hepsiburada", "amazon", "n11"],
  electronics: ["vatanbilgisayar", "itopya", "mediamarkt", "teknosa", "trendyol", "hepsiburada", "amazon", "n11"],
  fashion: ["lcwaikiki", "defacto", "zara", "boyner", "koton", "mavi", "trendyol", "hepsiburada", "amazon", "n11"],
  cosmetics: ["gratis", "rossmann", "trendyol", "hepsiburada", "amazon", "n11"],
  supplement: ["supplementler", "proteinocean", "trendyol", "hepsiburada", "amazon", "n11"]
};

function getPricesForOptimizerItem(name) {
  const lower = name.toLowerCase();
  const category = getItemCategory(name);
  const stores = CATEGORY_STORES[category] || CATEGORY_STORES.grocery;
  
  let basePrice = 50.00;
  if (category === "electronics") {
    basePrice = 2500.00;
    if (lower.includes("kulaklık") || lower.includes("mouse") || lower.includes("klavye")) {
      basePrice = 450.00;
    }
  } else if (category === "supplement") {
    basePrice = 1200.00;
    if (lower.includes("whey") || lower.includes("hardline") || lower.includes("protein")) {
      basePrice = 2200.00;
    }
  } else if (category === "fashion") {
    basePrice = 350.00;
    if (lower.includes("çorap") || lower.includes("corap")) {
      basePrice = 80.00;
    }
  } else if (category === "cosmetics") {
    basePrice = 180.00;
    if (lower.includes("parfüm") || lower.includes("parfum")) {
      basePrice = 950.00;
    }
  } else {
    if (lower.includes("yağ") || lower.includes("yag") || lower.includes("yudum")) {
      basePrice = 185.00;
    } else if (lower.includes("süt") || lower.includes("sut")) {
      basePrice = 28.00;
    } else if (lower.includes("peynir")) {
      basePrice = 85.00;
    } else if (lower.includes("un")) {
      basePrice = 75.00;
    } else if (lower.includes("çay") || lower.includes("cay")) {
      basePrice = 140.00;
    } else if (lower.includes("şeker") || lower.includes("seker")) {
      basePrice = 140.00;
    }
  }
  
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
  
  const prices = {};
  stores.forEach((store, idx) => {
    const variance = 0.85 + ((Math.abs(hash + idx * 7) % 30) / 100);
    prices[store] = Math.round(basePrice * variance * 100) / 100;
  });
  
  return prices;
}

const OFFLINE_COUPONS = [
  { store: "migros", code: "MIGR50", description: "500 TL üzeri 50 TL", discount: 50, min_amount: 500 },
  { store: "metro", code: "METRO150", description: "1500 TL üzeri 150 TL", discount: 150, min_amount: 1500 },
  { store: "carrefoursa", code: "CRF75", description: "750 TL üzeri 75 TL", discount: 75, min_amount: 750 },
  { store: "gratis", code: "GRATIS30", description: "300 TL üzeri 30 TL", discount: 30, min_amount: 300 },
];

let couponsCached = null;

async function createCoupon(event) {
  event.preventDefault();
  const payload = {
    store: document.getElementById("couponStore").value,
    code: document.getElementById("couponCode").value.trim(),
    min_amount: Number(document.getElementById("couponMinAmount").value || 0),
    discount: Number(document.getElementById("couponDiscount").value || 0),
    description: "",
    active: true,
  };
  if (!payload.code || payload.discount <= 0) return;
  try {
    await api("/api/coupons", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    couponsCached = null;
    event.target.reset();
    showToast("Kupon kaydedildi.");
    renderCart();
  } catch (error) {
    showToast(`Kupon kaydedilemedi: ${error.message}`);
  }
}

async function deleteCoupon(couponId) {
  try {
    await api(`/api/coupons/${couponId}`, { method: "DELETE" });
    couponsCached = null;
    showToast("Kupon silindi.");
    renderCart();
  } catch (error) {
    showToast(`Kupon silinemedi: ${error.message}`);
  }
}

function renderBackendOptimization(result, mode) {
  const resultsDiv = document.getElementById("optimizerResults");
  if (!resultsDiv || !result?.single_store || !result?.split_basket) return false;

  if (mode === "single") {
    const option = result.single_store;
    resultsDiv.innerHTML = `
      <div class="optimizer-summary">
        <span class="optimizer-kicker">EN UCUZ TEK MARKET</span>
        <h4>${currency.format(option.total)}</h4>
        <p><strong>${escapeHtml(option.store.toUpperCase())}</strong> ile
          ${currency.format(option.savings)} tasarruf.</p>
        ${option.coupon ? `<p class="coupon-applied">${escapeHtml(option.coupon.code)} kuponu: -${currency.format(option.coupon.discount)}</p>` : ""}
      </div>
      <div class="opt-store-card">
        ${option.items.map(item => `
          <div class="opt-item-row">
            <span>${escapeHtml(item.name)}${item.quantity > 1 ? ` x${item.quantity}` : ""}</span>
            <span class="opt-item-price">${currency.format(item.line_total)}</span>
          </div>
        `).join("")}
      </div>
    `;
    return true;
  }

  const split = result.split_basket;
  resultsDiv.innerHTML = `
    <div class="optimizer-summary">
      <span class="optimizer-kicker">BÖLÜNMÜŞ SEPET</span>
      <h4>${currency.format(split.total)}</h4>
      <p>En ucuz tek markete göre ek ${currency.format(split.savings)} tasarruf.</p>
    </div>
    <div class="optimizer-store-list">
      ${split.stores.map(group => `
        <div class="opt-store-card">
          <div class="opt-store-header">
            <span class="opt-store-name">${escapeHtml(group.store.toUpperCase())}</span>
            <span class="opt-store-total">${currency.format(group.total)}</span>
          </div>
          ${group.coupon ? `<p class="coupon-applied">${escapeHtml(group.coupon.code)}: -${currency.format(group.coupon.discount)}</p>` : ""}
          ${group.items.map(item => `
            <div class="opt-item-row">
              <span>
                ${escapeHtml(item.name)}
                ${item.unit_analysis ? `<small>${currency.format(item.unit_analysis.unit_price)} / ${escapeHtml(item.unit_analysis.unit)}</small>` : ""}
              </span>
              <span class="opt-item-price">${currency.format(item.line_total)}</span>
            </div>
          `).join("")}
        </div>
      `).join("")}
    </div>
  `;
  return true;
}

async function renderCart() {
  const listDiv = document.getElementById("cartItemsList");
  if (!listDiv) return;

  const statusContainer = document.getElementById("sharedListStatusContainer");
  if (statusContainer) {
    if (state.sharedListId) {
      statusContainer.innerHTML = `
        <div class="shared-list-badge" style="display:flex; justify-content:space-between; align-items:center; background: rgba(34, 197, 94, 0.1); border: 1px solid rgb(34, 197, 94); border-radius: 8px; padding: 10px 16px; margin-bottom: 20px; font-size: 13px; color: var(--ink);">
          <div style="display:flex; align-items:center; gap:8px; color: rgb(21, 128, 61);">
            <span style="width:8px; height:8px; border-radius:50%; background: rgb(34, 197, 94); display:inline-block; animation: pulse 1s infinite alternate;"></span>
            <strong>Canlı Ortak Liste Aktif</strong> (Kod: ${state.sharedListId})
          </div>
          <div style="display:flex; gap:10px;">
            <button type="button" class="text-button" onclick="shareCartList()" style="padding: 4px 8px; font-size: 12px; height: auto;">
              <i data-lucide="copy" style="width: 12px; height: 12px;"></i> Bağlantıyı Al
            </button>
            <button type="button" class="text-button btn-danger" onclick="leaveSharedList()" style="padding: 4px 8px; font-size: 12px; height: auto; color: var(--red);">
              <i data-lucide="log-out" style="width: 12px; height: 12px;"></i> Ayrıl
            </button>
          </div>
        </div>
      `;
    } else {
      statusContainer.innerHTML = "";
    }
  }

  // 1. Render items list
  if (state.cart.length === 0) {
    listDiv.innerHTML = `<p class="empty-text">Henüz ürün eklenmedi.</p>`;
  } else {
    listDiv.innerHTML = state.cart.map(item => `
      <div class="cart-item ${item.checked ? "checked" : ""}">
        <div class="cart-item-left">
          <input type="checkbox" ${item.checked ? "checked" : ""} onclick="toggleCartItem('${item.id}')">
          <span class="cart-item-name">${escapeHtml(item.name)}</span>
          <input
            class="cart-quantity"
            type="number"
            min="1"
            max="99"
            value="${Number.parseInt(item.quantity, 10) || 1}"
            aria-label="${escapeHtml(item.name)} adedi"
            onchange="updateCartQuantity('${item.id}', this.value)"
          >
        </div>
        <button class="cart-item-remove" onclick="removeCartItem('${item.id}')">
          <i data-lucide="trash-2" style="width: 16px; height: 16px;"></i>
        </button>
      </div>
    `).join("");
    lucide.createIcons();
  }

  // 2. Render coupons
  const couponsDiv = document.getElementById("cartCouponsList");
  if (couponsDiv) {
    if (!couponsCached) {
      try {
        couponsCached = await api("/api/coupons");
      } catch {
        couponsCached = OFFLINE_COUPONS;
      }
    }
    if (couponsCached.length === 0) {
      couponsDiv.innerHTML = `<p class="empty-text">Aktif kupon yok.</p>`;
    } else {
      couponsDiv.innerHTML = couponsCached.map(c => `
        <div class="coupon-card">
          <span class="coupon-code">${escapeHtml(c.code)}</span>
          <p class="coupon-desc">${escapeHtml(c.description)}</p>
          ${c.id ? `
            <button class="coupon-delete" onclick="deleteCoupon('${c.id}')" title="Kuponu sil" aria-label="${escapeHtml(c.code)} kuponunu sil">
              <i data-lucide="trash-2"></i>
            </button>
          ` : ""}
        </div>
      `).join("");
      lucide.createIcons();
    }
  }

  // 3. Run and Render Optimization Results
  const resultsDiv = document.getElementById("optimizerResults");
  if (!resultsDiv) return;

  if (state.cart.length === 0) {
    resultsDiv.innerHTML = `<p class="empty-text">Listeye ürün ekleyerek karşılaştırın.</p>`;
    return;
  }

  const uncheckedItems = state.cart.filter(item => !item.checked);
  if (uncheckedItems.length === 0) {
    resultsDiv.innerHTML = `<p class="empty-text">Tüm ürünler satın alınmış veya işaretlenmiş.</p>`;
    return;
  }

  if (navigator.onLine) {
    try {
      const optimized = await api("/api/cart/optimize", {
        method: "POST",
        body: JSON.stringify({
          items: uncheckedItems.map(item => ({
            id: item.id,
            name: item.name,
            quantity: Number.parseInt(item.quantity, 10) || 1,
            offers: item.offers || null,
          })),
        }),
      });
      localStorage.setItem("almadan_last_optimizer_result", JSON.stringify(optimized));
      if (renderBackendOptimization(optimized, state.optimizerMode)) return;
    } catch (error) {
      console.warn("Sunucu optimizasyonu kullanılamadı, yerel motora dönülüyor:", error.message);
    }
  } else {
    const cached = JSON.parse(localStorage.getItem("almadan_last_optimizer_result") || "null");
    if (cached && renderBackendOptimization(cached, state.optimizerMode)) return;
  }

  if (state.optimizerMode === "single") {
    // Single Store Mode (Category-based Single Store Optimization):
    // Group unchecked items by category
    const catGroups = {};
    uncheckedItems.forEach(item => {
      const cat = getItemCategory(item.name);
      if (!catGroups[cat]) catGroups[cat] = [];
      catGroups[cat].push(item);
    });

    const categoryOptimizations = [];
    let grandTotal = 0;

    Object.entries(catGroups).forEach(([cat, items]) => {
      const stores = CATEGORY_STORES[cat] || CATEGORY_STORES.grocery;
      const storeTotals = [];

      stores.forEach(store => {
        let subtotal = 0;
        const breakdowns = [];
        items.forEach(item => {
          const prices = getPricesForOptimizerItem(item.name);
          const price = prices[store] || prices[stores[0]] || 50.00;
          subtotal += price;
          breakdowns.push({ name: item.name, price });
        });

        // Apply store-specific coupons
        let couponDiscount = 0;
        if (couponsCached) {
          const coupon = couponsCached.find(c => c.store === store);
          if (coupon && subtotal >= coupon.min_amount) {
            couponDiscount = coupon.discount;
            subtotal -= couponDiscount;
          }
        }

        storeTotals.push({ store, subtotal, breakdowns, couponDiscount });
      });

      storeTotals.sort((a, b) => a.subtotal - b.subtotal);
      categoryOptimizations.push({
        category: cat,
        best: storeTotals[0],
        options: storeTotals
      });
      grandTotal += storeTotals[0].subtotal;
    });

    // Translate category labels
    const catLabels = {
      grocery: "Gıda & Market",
      electronics: "Elektronik",
      fashion: "Giyim & Moda",
      cosmetics: "Kozmetik & Kişisel Bakım",
      supplement: "Sporcu Takviyeleri"
    };

    resultsDiv.innerHTML = `
      <div style="padding: 14px; background: rgba(40,122,80,0.06); border: 1px solid var(--green); border-radius: 8px; margin-bottom: 14px;">
        <span style="font-size: 11px; font-weight: 800; color: var(--green);">KATEGORİ BAZLI EN AVANTAJLI SEÇENEK</span>
        <h4 style="font-family: 'Manrope', sans-serif; font-size: 22px; font-weight: 800; margin: 4px 0 0 0; color: var(--green-dark);">
          ${currency.format(grandTotal)}
        </h4>
        <div style="font-size: 13px; margin-top: 6px; color: var(--ink);">
          Kategorileri en ucuz tekil mağazalarından alarak toplam <strong>${currency.format(grandTotal)}</strong> ödersiniz.
        </div>
      </div>
      
      <div style="display: flex; flex-direction: column; gap: 14px;">
        ${categoryOptimizations.map(opt => `
          <div style="background: var(--bg-card); border: 1px solid var(--line); border-radius: 8px; padding: 12px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
              <span style="font-weight: 800; font-size: 13px; color: var(--green-dark);">${catLabels[opt.category] || opt.category.toUpperCase()}</span>
              <span style="font-size: 12px; font-weight: 700; background: rgba(40,122,80,0.1); color: var(--green-dark); padding: 2px 6px; border-radius: 4px;">
                ${opt.best.store.toUpperCase()}: ${currency.format(opt.best.subtotal)}
              </span>
            </div>
            ${opt.best.couponDiscount > 0 ? `<div style="font-size:11px; color:var(--green); font-weight:600; margin-bottom:6px;">-${opt.best.couponDiscount} TL Kupon Uygulandı</div>` : ""}
            <div style="display: flex; flex-direction: column; gap: 4px; border-top: 1px solid var(--line); padding-top: 6px;">
              ${opt.best.breakdowns.map(b => `
                <div class="opt-item-row" style="font-size: 12px;">
                  <span>${escapeHtml(b.name)}</span>
                  <span class="opt-item-price">${currency.format(b.price)}</span>
                </div>
              `).join("")}
            </div>
            
            <div style="margin-top: 8px; font-size: 11px; color: var(--ink-light); display: flex; gap: 6px; flex-wrap: wrap;">
              <span>Alternatifler:</span>
              ${opt.options.slice(1, 4).map(o => `
                <span style="background: var(--bg-app); padding: 1px 4px; border-radius: 3px;">
                  ${o.store}: ${currency.format(o.subtotal)}
                </span>
              `).join("")}
            </div>
          </div>
        `).join("")}
      </div>
    `;
  } else {
    // Split Store Optimizer:
    const splitItems = [];
    
    uncheckedItems.forEach(item => {
      const cat = getItemCategory(item.name);
      const stores = CATEGORY_STORES[cat] || CATEGORY_STORES.grocery;
      const prices = getPricesForOptimizerItem(item.name);
      
      let cheapestStore = stores[0];
      let cheapestPrice = Infinity;
      
      stores.forEach(store => {
        const price = prices[store];
        if (price !== undefined && price < cheapestPrice) {
          cheapestPrice = price;
          cheapestStore = store;
        }
      });
      
      splitItems.push({
        name: item.name,
        store: cheapestStore,
        price: cheapestPrice,
        category: cat
      });
    });

    const grouped = {};
    splitItems.forEach(si => {
      if (!grouped[si.store]) grouped[si.store] = { total: 0, items: [] };
      grouped[si.store].items.push(si);
      grouped[si.store].total += si.price;
    });

    let absoluteTotal = 0;
    let totalCouponDiscounts = 0;
    Object.keys(grouped).forEach(store => {
      if (couponsCached) {
        const coupon = couponsCached.find(c => c.store === store);
        if (coupon && grouped[store].total >= coupon.min_amount) {
          grouped[store].total -= coupon.discount;
          totalCouponDiscounts += coupon.discount;
        }
      }
      absoluteTotal += grouped[store].total;
    });

    // Calculate best single category sum to find split benefit
    let catTotalsSum = 0;
    const catGroups = {};
    uncheckedItems.forEach(item => {
      const cat = getItemCategory(item.name);
      if (!catGroups[cat]) catGroups[cat] = [];
      catGroups[cat].push(item);
    });

    Object.entries(catGroups).forEach(([cat, items]) => {
      const stores = CATEGORY_STORES[cat] || CATEGORY_STORES.grocery;
      const storeSums = [];
      stores.forEach(store => {
        let sum = 0;
        items.forEach(item => {
          const prices = getPricesForOptimizerItem(item.name);
          sum += prices[store] || prices[stores[0]] || 50.00;
        });
        if (couponsCached) {
          const coupon = couponsCached.find(c => c.store === store);
          if (coupon && sum >= coupon.min_amount) sum -= coupon.discount;
        }
        storeSums.push(sum);
      });
      catTotalsSum += Math.min(...storeSums);
    });

    const splitBenefit = Math.max(0, catTotalsSum - absoluteTotal);

    resultsDiv.innerHTML = `
      <div style="padding: 14px; background: rgba(40,122,80,0.06); border: 1px solid var(--green); border-radius: 8px; margin-bottom: 14px;">
        <span style="font-size: 11px; font-weight: 800; color: var(--green);">BÖLÜNMÜŞ SEPET EN İYİ DEĞER</span>
        <h4 style="font-family: 'Manrope', sans-serif; font-size: 22px; font-weight: 800; margin: 4px 0 0 0; color: var(--green-dark);">
          ${currency.format(absoluteTotal)}
        </h4>
        <div style="font-size: 13px; margin-top: 6px; color: var(--ink);">
          En iyi tekil mağaza toplamına kıyasla sepeti bölerek ek olarak <strong>${currency.format(splitBenefit)}</strong> kâr ediyorsunuz.
        </div>
      </div>
      
      <div style="display: flex; flex-direction: column; gap: 10px;">
        ${Object.entries(grouped).map(([store, data]) => `
          <div class="opt-store-card">
            <div class="opt-store-header">
              <span class="opt-store-name" style="color: var(--green-dark);">${escapeHtml(store.toUpperCase())} Mağazasından Alınacaklar</span>
              <span class="opt-store-total">${currency.format(data.total)}</span>
            </div>
            <div style="border-top: 1px solid var(--line); padding-top: 6px;">
              ${data.items.map(item => `
                <div class="opt-item-row">
                  <span>${escapeHtml(item.name)}</span>
                  <span class="opt-item-price">${currency.format(item.price)}</span>
                </div>
              `).join("")}
            </div>
          </div>
        `).join("")}
      </div>
    `;
  }
}


/* COLLABORATIVE REAL-TIME SHARING POLING */
function showShareLinkDialog(shareUrl) {
  const dialog = document.getElementById("productDialog");
  const content = document.getElementById("dialogContent");
  if (!dialog || !content) return;
  
  content.innerHTML = `
    <div class="dialog-body auth-dialog">
      <p class="eyebrow">ORTAK LİSTE</p>
      <h2>Ailenizle Birlikte Düzenleyin.</h2>
      <p class="auth-copy" style="margin-bottom: 16px; font-size: 13px; color: var(--ink-light);">Aşağıdaki bağlantıyı kopyalayarak ailenize veya arkadaşlarınıza gönderin. Herkes listeye eş zamanlı ürün ekleyip silebilir!</p>
      <div class="manual-fields">
        <label class="manual-field">
          <span>Paylaşım Linki</span>
          <input id="shareListUrlInput" type="text" value="${escapeHtml(shareUrl)}" readonly style="width: 100%; min-height: 44px; padding: 0 12px; border: 1px solid var(--line); border-radius: 6px; background: var(--bg-hover); font-family: inherit; font-size: 14px; color: var(--ink);">
        </label>
      </div>
      <div class="dialog-actions" style="margin-top: 20px;">
        <button class="secondary-button" type="button" onclick="closeDialog()">Kapat</button>
        <button class="primary-button" type="button" onclick="copyShareLinkInput()">
          <i data-lucide="copy"></i>
          Linki Kopyala
        </button>
      </div>
    </div>
  `;
  dialog.showModal();
  lucide.createIcons();
}

window.copyShareLinkInput = function() {
  const input = document.getElementById("shareListUrlInput");
  if (input) {
    input.select();
    input.setSelectionRange(0, 99999); // Mobil için
    try {
      document.execCommand("copy");
      showToast("Bağlantı kopyalandı!");
    } catch (err) {
      showToast("Bağlantı kopyalanamadı, lütfen elle kopyalayın.");
    }
  }
};

function leaveSharedList() {
  if (confirm("Ortak listeden ayrılmak istediğinize emin misiniz? Kendi yerel sepetinize geri döneceksiniz.")) {
    if (pollingInterval) {
      clearInterval(pollingInterval);
      pollingInterval = null;
    }
    state.sharedListId = null;
    state.sharedListVersion = 0;
    
    // Remove query parameter from URL without page reload
    const url = new URL(window.location.href);
    url.searchParams.delete("list");
    window.history.replaceState({}, document.title, url.toString());
    
    // Load cart back from local storage
    state.cart = JSON.parse(localStorage.getItem("almadan_cart") || "[]");
    renderCart();
    showToast("Ortak listeden ayrılındı. Yerel sepetinize geçildi.");
  }
}

async function shareCartList() {
  if (state.cart.length === 0) {
    showToast("Sepetiniz boş, paylaşmak için önce ürün ekleyin.");
    return;
  }

  showToast("Paylaşım linki hazırlanıyor...");
  try {
    const res = await api("/api/lists", {
      method: "POST",
      body: JSON.stringify({ items: state.cart })
    });
    
    state.sharedListId = res.id;
    state.sharedListVersion = res.version || 1;
    const shareUrl = `${window.location.origin}/?list=${res.id}`;
    
    // Attempt automatic clipboard copy
    let copied = false;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      try {
        await navigator.clipboard.writeText(shareUrl);
        copied = true;
      } catch (e) {
        console.warn("Navigator clipboard failed, falling back", e);
      }
    }
    
    // Show copy result toast if auto-copied
    if (copied) {
      showToast("Bağlantı panoya kopyalandı!");
    }
    
    // Always open share dialog so user can see the link and copy manually if needed
    showShareLinkDialog(shareUrl);
    renderCart(); // Update UI to show active status
    
    // Start Polling loop if not active
    startPolling();
  } catch (error) {
    showToast(error.message);
  }
}

async function checkSharedListUrl() {
  const params = new URLSearchParams(window.location.search);
  const listId = params.get("list");
  if (listId) {
    state.sharedListId = listId;
    showToast("Ortak aile listesi yüklendi. Canlı senkronizasyon aktif!");
    
    try {
      const res = await api(`/api/lists/${listId}`);
      state.cart = res.items || [];
      state.sharedListVersion = res.version || 1;
      saveCartToLocalStorage();
      switchView("cart");
      renderCart(); // Make sure cart items are instantly drawn on screen!
      
      startPolling();
    } catch (error) {
      showToast("Paylaşılan liste yüklenemedi: " + error.message);
    }
  }
}

async function syncSharedListWithServer() {
  if (!state.sharedListId) return;
  const payload = {
    items: state.cart,
    base_version: state.sharedListVersion,
  };
  if (!navigator.onLine) {
    localStorage.setItem("almadan_pending_shared_sync", JSON.stringify({
      listId: state.sharedListId,
      payload,
    }));
    return;
  }
  try {
    const res = await api(`/api/lists/${state.sharedListId}`, {
      method: "PUT",
      body: JSON.stringify(payload)
    });
    state.cart = res.items || state.cart;
    state.sharedListVersion = res.version || state.sharedListVersion + 1;
    saveCartToLocalStorage();
    localStorage.removeItem("almadan_pending_shared_sync");
  } catch (error) {
    console.error("Ortak liste sunucuyla eşitlenemedi:", error.message);
    localStorage.setItem("almadan_pending_shared_sync", JSON.stringify({
      listId: state.sharedListId,
      payload,
    }));
  }
}

async function flushPendingSharedSync() {
  const pending = JSON.parse(localStorage.getItem("almadan_pending_shared_sync") || "null");
  if (!pending || !navigator.onLine) return;
  state.sharedListId = pending.listId || state.sharedListId;
  try {
    const res = await api(`/api/lists/${pending.listId}`, {
      method: "PUT",
      body: JSON.stringify(pending.payload),
    });
    state.cart = res.items || state.cart;
    state.sharedListVersion = res.version || state.sharedListVersion;
    saveCartToLocalStorage();
    localStorage.removeItem("almadan_pending_shared_sync");
    renderCart();
    showToast("Çevrimdışı liste değişiklikleri eşitlendi.");
  } catch (error) {
    console.warn("Bekleyen ortak liste eşitlenemedi:", error.message);
  }
}

let pollingInterval = null;

function startPolling() {
  if (pollingInterval) clearInterval(pollingInterval);
  pollingInterval = setInterval(async () => {
    if (!state.sharedListId || state.activeView !== "cart") return;
    try {
      const res = await api(`/api/lists/${state.sharedListId}`);
      state.sharedListVersion = res.version || state.sharedListVersion;
      // Simple compare to prevent unnecessary redraws
      if (JSON.stringify(res.items) !== JSON.stringify(state.cart)) {
        state.cart = res.items || [];
        saveCartToLocalStorage();
        renderCart();
      }
    } catch (error) {
      console.warn("Canlı veri eşitleme başarısız:", error.message);
    }
  }, 5000);
}


/* WEB SPEECH API VOICE DICTATION */
function startVoiceSearch() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    showToast("Tarayıcınız ses tanımayı desteklemiyor.");
    return;
  }

  const recognition = new SpeechRecognition();
  recognition.lang = "tr-TR";
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;

  const micBtn = document.getElementById("micButton");
  micBtn.classList.add("recording");
  showToast("Dinleniyor... Ürün adını söyleyin.");

  recognition.start();

  recognition.onresult = (event) => {
    const result = event.results[0][0].transcript;
    document.getElementById("productUrl").value = result;
    showToast(`Tanımlandı: "${result}"`);
    // Automatically submit search
    document.getElementById("urlForm").dispatchEvent(new Event("submit"));
  };

  recognition.onerror = (event) => {
    showToast("Ses tanınamadı. Lütfen tekrar deneyin.");
  };

  recognition.onend = () => {
    micBtn.classList.remove("recording");
  };
}


/* KATEGORİ DEĞİŞİMİ VE AI CİLT ANALİZİ LOGIC */
let currentSkinType = null; // light, medium, dark

function displaySkinAnalysis(type, showToastMsg = false) {
  currentSkinType = type;
  const resultCard = document.getElementById("aiAnalysisResultCard");
  const toneIndicator = document.getElementById("aiSkinToneColorIndicator");
  const toneName = document.getElementById("aiSkinToneName");
  const toneTag = document.getElementById("aiSkinToneTag");
  const paletteDiv = document.getElementById("aiPaletteColors");
  const statusEl = document.getElementById("aiUploadStatus");
  const laserEl = document.getElementById("aiScanLaser");
  const cameraIcon = document.getElementById("aiCameraIcon");

  if (laserEl) laserEl.classList.add("hidden");
  if (cameraIcon) cameraIcon.style.animation = "";
  if (statusEl) {
    const labels = { light: "Açık Tenli Model", medium: "Buğday Tenli Model", dark: "Esmer Model" };
    statusEl.innerHTML = `<span style="color: var(--green);">Kayıtlı Analiz Yüklendi!</span> (${labels[type] || 'Kendi Analiziniz'})`;
  }
  
  let colorHex = "#fdf5e6";
  let colorName = "Açık / Porselen";
  let undertone = "Soğuk Alt Ton";
  let paletteHtml = "";
  
  if (type === "light") {
    colorHex = "#fbe3d3";
    colorName = "Açık / Porselen Fildişi";
    undertone = "Soğuk Alt Ton";
    paletteHtml = `
      <div style="display:flex; flex-direction:column; align-items:center; font-size:10px;">
        <span style="width:30px; height:30px; border-radius:50%; background:#e06666; border:1px solid var(--line); display:inline-block;"></span>
        <span style="margin-top:4px;">Gül Kurusu Ruj</span>
      </div>
      <div style="display:flex; flex-direction:column; align-items:center; font-size:10px;">
        <span style="width:30px; height:30px; border-radius:50%; background:#ea9999; border:1px solid var(--line); display:inline-block;"></span>
        <span style="margin-top:4px;">Toz Pembe Allık</span>
      </div>
      <div style="display:flex; flex-direction:column; align-items:center; font-size:10px;">
        <span style="width:30px; height:30px; border-radius:50%; background:#d5a6bd; border:1px solid var(--line); display:inline-block;"></span>
        <span style="margin-top:4px;">Eflatun Göz Farı</span>
      </div>
    `;
  } else if (type === "medium") {
    colorHex = "#e8c39e";
    colorName = "Buğday / Doğal Kumral";
    undertone = "Sıcak Alt Ton";
    paletteHtml = `
      <div style="display:flex; flex-direction:column; align-items:center; font-size:10px;">
        <span style="width:30px; height:30px; border-radius:50%; background:#c00000; border:1px solid var(--line); display:inline-block;"></span>
        <span style="margin-top:4px;">Kiremit Kırmızısı</span>
      </div>
      <div style="display:flex; flex-direction:column; align-items:center; font-size:10px;">
        <span style="width:30px; height:30px; border-radius:50%; background:#f6b26b; border:1px solid var(--line); display:inline-block;"></span>
        <span style="margin-top:4px;">Şeftali Allık</span>
      </div>
      <div style="display:flex; flex-direction:column; align-items:center; font-size:10px;">
        <span style="width:30px; height:30px; border-radius:50%; background:#b45f06; border:1px solid var(--line); display:inline-block;"></span>
        <span style="margin-top:4px;">Bronz Far</span>
      </div>
    `;
  } else if (type === "dark") {
    colorHex = "#a87a51";
    colorName = "Esmer / Karamel Kahve";
    undertone = "Nötr & Sıcak Alt Ton";
    paletteHtml = `
      <div style="display:flex; flex-direction:column; align-items:center; font-size:10px;">
        <span style="width:30px; height:30px; border-radius:50%; background:#741b47; border:1px solid var(--line); display:inline-block;"></span>
        <span style="margin-top:4px;">Mürdüm Ruj</span>
      </div>
      <div style="display:flex; flex-direction:column; align-items:center; font-size:10px;">
        <span style="width:30px; height:30px; border-radius:50%; background:#a64d79; border:1px solid var(--line); display:inline-block;"></span>
        <span style="margin-top:4px;">Koyu Mürdüm Allık</span>
      </div>
      <div style="display:flex; flex-direction:column; align-items:center; font-size:10px;">
        <span style="width:30px; height:30px; border-radius:50%; background:#783f04; border:1px solid var(--line); display:inline-block;"></span>
        <span style="margin-top:4px;">Bakır Göz Farı</span>
      </div>
    `;
  }
  
  if (toneIndicator) toneIndicator.style.backgroundColor = colorHex;
  if (toneName) toneName.innerText = colorName;
  if (toneTag) toneTag.innerText = undertone;
  if (paletteDiv) paletteDiv.innerHTML = paletteHtml;
  
  if (resultCard) resultCard.classList.remove("hidden");
  
  const answerBox = document.getElementById("aiColorAnswerBox");
  const questionInput = document.getElementById("aiColorQuestionInput");
  if (answerBox) answerBox.classList.add("hidden");
  if (questionInput) questionInput.value = "";
  
  if (showToastMsg) {
    showToast("Cilt tonu analiz edildi! Soru sorma paneli aktif.");
  }
}

function handleCategoryChange() {
  const selector = document.getElementById("searchCategorySelector");
  if (!selector) return;
  const category = selector.value;
  const aiSection = document.getElementById("aiCosmeticsSection");
  if (!aiSection) return;
  
  if (category === "cosmetics") {
    aiSection.classList.remove("hidden");
    lucide.createIcons();
    // Auto-load previously saved skin analysis if it exists
    if (state.auth.authenticated && state.auth.user && state.auth.user.skin_type) {
      displaySkinAnalysis(state.auth.user.skin_type, false);
    } else {
      const guestSkinType = localStorage.getItem("almadan_skin_type");
      if (guestSkinType) {
        displaySkinAnalysis(guestSkinType, false);
      }
    }
  } else {
    aiSection.classList.add("hidden");
  }
}

function runAiSkinScan(type) {
  const statusEl = document.getElementById("aiUploadStatus");
  const laserEl = document.getElementById("aiScanLaser");
  const resultCard = document.getElementById("aiAnalysisResultCard");
  const cameraIcon = document.getElementById("aiCameraIcon");
  
  // Reset previous result
  resultCard.classList.add("hidden");
  laserEl.classList.remove("hidden");
  cameraIcon.style.animation = "pulse 1s infinite alternate";
  
  if (type === "uploaded") {
    statusEl.innerHTML = `<span style="color: var(--green);">Fotoğraf Yüklendi!</span> Analiz ediliyor...`;
    const types = ["light", "medium", "dark"];
    currentSkinType = types[Math.floor(Math.random() * types.length)];
  } else {
    currentSkinType = type;
    const labels = { light: "Açık Tenli Model", medium: "Buğday Tenli Model", dark: "Esmer Model" };
    statusEl.innerHTML = `<strong style="color: var(--green-dark);">${labels[type]}</strong> analiz ediliyor...`;
  }
  
  // Simulate scan (laser line sweeps up and down using CSS keyframes)
  laserEl.style.animation = "scanLaserAnim 1.5s infinite ease-in-out";
  
  setTimeout(() => {
    // Show analysis details
    displaySkinAnalysis(currentSkinType, true);
    
    // Save to localStorage
    localStorage.setItem("almadan_skin_type", currentSkinType);
    
    // Save to authenticated user profile
    if (state.auth.authenticated && state.auth.user) {
      api("/auth/profile", {
        method: "PUT",
        body: JSON.stringify({
          gender: state.auth.user.gender || "belirtilmemiş",
          phone: state.auth.user.phone || "",
          notification_pref: state.auth.user.notification_pref || "both",
          silence_enabled: !!state.auth.user.silence_hours,
          skin_type: currentSkinType
        })
      }).then(result => {
        state.auth.user = result.user;
      }).catch(err => {
        console.error("Skin type could not be saved to profile:", err);
      });
    }
  }, 2000);
}

function askAiColorSuitability() {
  const query = document.getElementById("aiColorQuestionInput").value.trim().toLowerCase();
  const answerBox = document.getElementById("aiColorAnswerBox");
  
  if (!query) {
    showToast("Lütfen analiz etmek istediğiniz bir renk veya makyaj ürünü yazın.");
    return;
  }
  
  if (!currentSkinType) {
    showToast("Lütfen önce bir fotoğraf yükleyin veya model seçerek cilt analizi yapın.");
    return;
  }
  
  answerBox.classList.remove("hidden");
  answerBox.innerHTML = `<em>Yapay zeka analiz ediyor...</em>`;
  
  setTimeout(() => {
    let comment = "";
    
    if (currentSkinType === "light") {
      if (query.includes("pembe") || query.includes("mor") || query.includes("eflatun") || query.includes("gül") || query.includes("berry") || query.includes("plum")) {
        comment = "✨ **Mükemmel Uyum!** Pembe ve gül kurusu tonları soğuk alt tonlu açık teninizle harika bir kontrast oluşturacaktır. Canlılık ve tazelik katacaktır.";
      } else if (query.includes("kiremit") || query.includes("bronz") || query.includes("turuncu") || query.includes("şeftali") || query.includes("seftali")) {
        comment = "⚠️ **Uyumsuz Olabilir:** Sıcak kiremit, bronz veya turuncu tonları soğuk alt tonlu teninizde mat ve yorgun durabilir. Bunun yerine soğuk pembe veya mürdüm tonlarına yönelmenizi öneririz.";
      } else {
        comment = "ℹ️ **Nötr Etki:** Yazdığınız renk açık teniniz için kullanılabilir fakat gözlerinizi veya dudaklarınızı çok ön plana çıkarmayacaktır. Açık tenliler için pembe/mor yansımalı tonlar daha canlı duracaktır.";
      }
    } else if (currentSkinType === "medium") {
      if (query.includes("şeftali") || query.includes("seftali") || query.includes("kiremit") || query.includes("bronz") || query.includes("turuncu") || query.includes("coral") || query.includes("mercan")) {
        comment = "✨ **Harika Uyum!** Şeftali, mercan ve kiremit tonları sıcak alt tonlu buğday teninizi mükemmel şekilde ısıtacak ve doğal bir ışıltı katacaktır.";
      } else if (query.includes("eflatun") || query.includes("toz pembe") || query.includes("soğuk pembe")) {
        comment = "⚠️ **Uyumsuz Olabilir:** Soğuk alt tonlu eflatun ve toz pembe renkleri sıcak buğday teninizle çakışarak cildinizi solgun gösterebilir. Şeftali ve toprak tonları daha uygundur.";
      } else {
        comment = "ℹ️ **Nötr Etki:** Yazdığınız ton buğday teninizle uyumludur. Ancak altın ve bronz ışıltılı makyaj bazlarıyla desteklerseniz etkiyi ikiye katlayabilirsiniz.";
      }
    } else { // dark
      comment = "ℹ️ **Uyum Analizi:** Esmer ten yapınız için toprak, mürdüm, bordo ve bakır tonları muazzam bir derinlik katacaktır. Açık pudra pembesi tonlar cildinizi gri gösterebileceğinden, sıcak alt tonlu kahve ve derin kırmızıları tercih edebilirsiniz.";
      if (query.includes("mürdüm") || query.includes("bordo") || query.includes("bakır") || query.includes("bakir") || query.includes("kahve") || query.includes("bronze") || query.includes("altın")) {
        comment = "✨ **Harika Uyum!** Derin mürdüm, bordo ve bakır yansımalı tonlar esmer teninizin asaletini ve sıcaklığını ön plana çıkaracaktır. Şiddetle tavsiye edilir.";
      }
    }
    
    answerBox.innerHTML = comment;
  }, 1000);
}
