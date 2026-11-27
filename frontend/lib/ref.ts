"use client";

// Реферальная атрибуция. Код из `?ref=CODE` сохраняется в localStorage при
// любом заходе и передаётся в auth-запрос как `ref_code` при входе/регистрации,
// после чего очищается. Минимально и неразрушающе.

const REF_KEY = "altsr_ref";

/** Запоминает `?ref=CODE` из текущего URL (если есть). Безопасно на сервере. */
export function captureRefFromUrl(): void {
  if (typeof window === "undefined") return;
  try {
    const code = new URLSearchParams(window.location.search).get("ref");
    if (code && code.trim()) window.localStorage.setItem(REF_KEY, code.trim().slice(0, 64));
  } catch {
    /* localStorage может быть недоступен — не ломаем страницу */
  }
}

/** Сохранённый реферальный код, если есть. */
export function getRef(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(REF_KEY);
  } catch {
    return null;
  }
}

/** Очищает код (после успешного входа/регистрации). */
export function clearRef(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(REF_KEY);
  } catch {
    /* no-op */
  }
}
