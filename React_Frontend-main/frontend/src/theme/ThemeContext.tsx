import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { LIGHT, DARK, type Palette } from './tokens'

interface ThemeContextValue {
  dark: boolean
  toggle: () => void
  colors: Palette
}

const ThemeContext = createContext<ThemeContextValue | null>(null)

const STORAGE_KEY = 'qgirs-dark-mode'

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [dark, setDark] = useState<boolean>(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY)
    if (stored !== null) return stored === 'true'
    return window.matchMedia('(prefers-color-scheme: dark)').matches
  })

  // Streamlit's T.set_mode() had to reassign module globals in place because
  // it couldn't re-import on rerun. React doesn't have that constraint: the
  // .dark class + CSS variables in index.css handle every consumer for free.
  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
    window.localStorage.setItem(STORAGE_KEY, String(dark))
  }, [dark])

  const value = useMemo<ThemeContextValue>(
    () => ({ dark, toggle: () => setDark((d) => !d), colors: dark ? DARK : LIGHT }),
    [dark],
  )

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}

export function useTheme() {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme must be used within a ThemeProvider')
  return ctx
}
