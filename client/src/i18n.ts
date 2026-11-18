import { i18n } from "@lingui/core";

export const locales = {
  en: "English",
  it: "Italiano",
  zh: "中文"
}

/**
 * We do a dynamic import of just the catalog that we need
 * @param locale any locale string
 */
export async function dynamicActivate(locale: string) {
  localStorage.setItem('vite-ui-locale', locale)
  
  const messages = await import(`./locales/${locale}/messages.po`)

  i18n.load(locale, messages.messages)
  i18n.activate(locale)
}