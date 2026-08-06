import { useEffect, useState } from 'react'

/** Returns `value` only after it has stopped changing for `delay` ms — for
 * search boxes whose value is sent to the server, so typing fires one request
 * at the end instead of one per keystroke. */
export function useDebounced<T>(value: T, delay = 350): T {
  const [debounced, setDebounced] = useState(value)

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])

  return debounced
}
