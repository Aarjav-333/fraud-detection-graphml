import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { getSystemInfo } from '../api/system'
import { pct } from '../utils/format'

const STANDALONE = 'standalone'
const NORMAL = { loaded: false, demoMode: '', mlUnavailableReason: null }
const RECHECK_AFTER_MS = 2000      // focus and the live connection can both ask at once
const MAX_RETRY_MS = 30000
const SystemContext = createContext(null)

// Which backend this is: the normal app, or the standalone demo. It asks on load,
// on login, when the tab regains focus and when the live connection reconnects,
// so switching backends (normal <-> --serve --standalone) shows without a reload.
// While the backend can't be reached the app behaves as normal and keeps retrying;
// an older backend without the endpoint is the normal app.
export function SystemProvider({ children }) {
  const [info, setInfo] = useState(NORMAL)
  const latest = useRef(0)
  const lastAsked = useRef(0)
  const retry = useRef({ timer: null, attempt: 0 })

  const refresh = useCallback(async () => {
    const request = ++latest.current
    lastAsked.current = Date.now()
    clearTimeout(retry.current.timer)
    const apply = (next) => {
      if (request !== latest.current) return   // a newer answer is on its way
      setInfo((prev) => (prev.loaded && prev.demoMode === next.demoMode
        && prev.mlUnavailableReason === next.mlUnavailableReason ? prev : { ...next, loaded: true }))
    }
    try {
      const d = await getSystemInfo()
      retry.current.attempt = 0
      apply({ demoMode: d.demo_mode || '', mlUnavailableReason: d.ml_unavailable_reason })
    } catch (err) {
      if (err.response) {   // it answered without the endpoint: an older, normal backend
        apply(NORMAL)
        return
      }
      if (request !== latest.current) return
      setInfo((prev) => (prev.loaded ? prev : { ...prev, loaded: true }))   // keep what we knew
      const delay = Math.min(MAX_RETRY_MS, 1000 * 2 ** retry.current.attempt)
      retry.current.attempt += 1
      retry.current.timer = setTimeout(refresh, delay)
    }
  }, [])

  useEffect(() => {
    refresh()
    const onFocus = () => {
      if (document.visibilityState === 'visible' && Date.now() - lastAsked.current > RECHECK_AFTER_MS) refresh()
    }
    window.addEventListener('focus', onFocus)
    document.addEventListener('visibilitychange', onFocus)
    const pending = retry.current
    return () => {
      window.removeEventListener('focus', onFocus)
      document.removeEventListener('visibilitychange', onFocus)
      clearTimeout(pending.timer)
    }
  }, [refresh])

  const value = useMemo(() => {
    const standalone = info.demoMode === STANDALONE
    return {
      ...info,
      standalone,
      refresh,
      // Model scores and ground-truth fraud labels exist only on the main dataset. Pages
      // show them through these, so the standalone demo never shows a made-up "0%" or "Legit".
      hasModelScores: !standalone,
      hasLabels: !standalone,
      modelScore: (value, digits = 1, absent = '—') => (standalone ? absent : pct(value, digits)),
    }
  }, [info, refresh])
  return <SystemContext.Provider value={value}>{children}</SystemContext.Provider>
}

export function useSystem() {
  return useContext(SystemContext)
}
