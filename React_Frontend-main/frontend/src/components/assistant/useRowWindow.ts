import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Which slice of a long row list is actually worth drawing.
 *
 * The table used to render every row it was given. An answer backed by a few
 * thousand rows therefore built a few thousand <tr> elements, each with one
 * <td> per column, and the browser had to lay all of them out before it could
 * paint anything - which is what made scrolling and typing in the filter boxes
 * choppy. The rows were never the problem; drawing them all at once was.
 *
 * So the DATA is untouched - sorting, filtering, column reorder and the CSV /
 * Excel exports all still see every row - and only the handful in front of the
 * user is put in the DOM. Two spacer rows above and below stand in for the rest
 * so the scrollbar still reflects the true length and jumping to the middle
 * lands where you expect.
 *
 * Rows here are uniform height (one line of text, fixed padding), which is what
 * makes the arithmetic this simple: the first visible row is scrollTop/rowHeight
 * and everything follows from that. If a cell ever wraps to two lines this
 * assumption breaks and a measuring virtualiser would be the right answer
 * instead.
 */
export interface RowWindow {
  /** Attach to the scrolling container. */
  scrollRef: React.RefObject<HTMLDivElement | null>
  /** First row index to render. */
  start: number
  /** One past the last row index to render. */
  end: number
  /** Pixel height standing in for the rows before `start`. */
  padTop: number
  /** Pixel height standing in for the rows after `end`. */
  padBottom: number
  /** True once the list is long enough that windowing is doing anything. */
  active: boolean
}

export function useRowWindow(
  rowCount: number,
  rowHeight = 33,
  /**
   * Rows drawn beyond the viewport on each side. Enough that a fast flick does
   * not show blank space before the next paint, small enough to stay cheap.
   */
  overscan = 12,
  /**
   * Below this many rows the whole list is rendered. Windowing costs a scroll
   * listener and re-renders, which is not worth it for a short table - and this
   * keeps Ctrl+F working normally for the everyday case.
   */
  threshold = 150,
): RowWindow {
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const [range, setRange] = useState({ start: 0, end: rowCount })

  const active = rowCount > threshold

  const recompute = useCallback(() => {
    const el = scrollRef.current
    if (!el || !active) {
      setRange({ start: 0, end: rowCount })
      return
    }
    const first = Math.floor(el.scrollTop / rowHeight)
    const visible = Math.ceil(el.clientHeight / rowHeight)
    const start = Math.max(0, first - overscan)
    const end = Math.min(rowCount, first + visible + overscan)
    setRange((prev) => (prev.start === start && prev.end === end ? prev : { start, end }))
  }, [active, rowCount, rowHeight, overscan])

  useEffect(() => {
    recompute()
    const el = scrollRef.current
    if (!el || !active) return

    // passive: this listener never calls preventDefault, and saying so lets the
    // browser scroll without waiting on it - the difference between smooth and
    // janky on a long list.
    el.addEventListener('scroll', recompute, { passive: true })

    // The window also has to be recut when the container resizes - opening the
    // sidebar or rotating a tablet changes how many rows fit.
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(recompute) : null
    ro?.observe(el)

    return () => {
      el.removeEventListener('scroll', recompute)
      ro?.disconnect()
    }
  }, [recompute, active])

  // Filtering or sorting replaces the list under the scroll position; start
  // again from the top rather than leaving the user in the middle of results
  // they have not seen.
  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = 0
    setRange({ start: 0, end: active ? Math.min(rowCount, 60) : rowCount })
  }, [rowCount, active])

  const start = active ? range.start : 0
  const end = active ? Math.min(range.end, rowCount) : rowCount

  return {
    scrollRef,
    start,
    end,
    padTop: active ? start * rowHeight : 0,
    padBottom: active ? Math.max(0, (rowCount - end) * rowHeight) : 0,
    active,
  }
}
