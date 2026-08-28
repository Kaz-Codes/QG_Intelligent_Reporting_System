import { useEffect, useRef, useState } from 'react'
import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'

import {
  NOTIFICATION_PAGE_SIZE,
  fetchUnreadCount,
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  subscribeToNotifications,
} from './notifications'

/**
 * React Query hooks for the notification bell and panel.
 *
 *
 * NOTHING HERE MAY BREAK THE PAGE.
 *
 * That is the constraint the whole file is written around. Notifications are
 * an ambient side feature living in the app header, so a failing
 * /notifications call must leave the header — and everything under it —
 * working. Three things enforce it:
 *
 *   throwOnError: false   React Query's default, but stated explicitly here
 *                         because it is load-bearing rather than incidental.
 *                         With it true, a 500 from the badge endpoint would
 *                         throw during render and the nearest error boundary
 *                         would blank the whole screen over a count nobody is
 *                         looking at.
 *   retry: false          A backend that is down should cost one failed
 *                         request per focus, not three with backoff. Matches
 *                         DASHBOARD_QUERY_OPTIONS.
 *   a count that falls    useUnreadCount returns 0 on error, so the bell
 *   back to zero          renders with no badge rather than no bell.
 *
 * The consumers then treat an error as "no notifications to show", never as a
 * reason to stop rendering.
 */

export const NOTIFICATION_KEYS = {
  unread: ['notifications', 'unread-count'] as const,
  list: ['notifications', 'list'] as const,
}

//--------------------------------
// THE BADGE
//--------------------------------

export function useUnreadCount() {
  const query = useQuery({
    queryKey: NOTIFICATION_KEYS.unread,
    queryFn: fetchUnreadCount,
    // Refetched whenever the user comes back to the tab. This is the fallback
    // path that makes the websocket optional: if the socket never connects,
    // the badge is still correct every time the window is focused — just less
    // promptly than a live push.
    refetchOnWindowFocus: true,
    staleTime: 30_000,
    retry: false,
    throwOnError: false,
  })

  return {
    // Never undefined and never an error to the caller: a bell with no badge
    // is the correct rendering of "we could not ask".
    count: query.isError ? 0 : (query.data ?? 0),
    isLoading: query.isLoading,
  }
}

//--------------------------------
// THE PANEL LIST
//
// Paged rather than infinite-in-one-go: the backend serves 20 at a time and
// the panel appends. `enabled` keeps the request from firing at all until the
// drawer is actually opened — the bell alone must cost one COUNT, not a page
// of rows for every user on every page load.
//--------------------------------

export function useNotificationList(enabled: boolean) {
  const query = useInfiniteQuery({
    queryKey: NOTIFICATION_KEYS.list,
    queryFn: ({ pageParam }) =>
      listNotifications({ page: pageParam, pageSize: NOTIFICATION_PAGE_SIZE }),
    initialPageParam: 1,
    getNextPageParam: (last) => {
      const { page, total_pages } = last.pagination
      return page < total_pages ? page + 1 : undefined
    },
    enabled,
    staleTime: 30_000,
    retry: false,
    throwOnError: false,
  })

  return {
    ...query,
    rows: query.data?.pages.flatMap((p) => p.rows) ?? [],
    total: query.data?.pages[0]?.pagination.total ?? 0,
  }
}

//--------------------------------
// MARKING READ
//
// Both mutations invalidate the badge AND the list, because the two are
// separate server-side reads and a stale badge beside a read row is exactly
// the kind of small wrongness that makes people distrust the feature.
//--------------------------------

export function useMarkRead() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: markNotificationRead,
    // Optimistic on the badge only. The row's own read state comes back with
    // the list refetch; the count is what the user is looking at as they
    // click, so it must move immediately.
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: NOTIFICATION_KEYS.unread })
      const previous = queryClient.getQueryData<number>(NOTIFICATION_KEYS.unread)
      queryClient.setQueryData<number>(NOTIFICATION_KEYS.unread, (n) =>
        Math.max(0, (n ?? 0) - 1),
      )
      return { previous }
    },
    onError: (_error, _id, context) => {
      // Put the count back. A failed mark-read must not silently lose a
      // notification from the badge while the row is still unread on the
      // server.
      if (context?.previous !== undefined) {
        queryClient.setQueryData(NOTIFICATION_KEYS.unread, context.previous)
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: NOTIFICATION_KEYS.unread })
      queryClient.invalidateQueries({ queryKey: NOTIFICATION_KEYS.list })
    },
  })
}

export function useMarkAllRead() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: markAllNotificationsRead,
    onSuccess: () => {
      queryClient.setQueryData(NOTIFICATION_KEYS.unread, 0)
      queryClient.invalidateQueries({ queryKey: NOTIFICATION_KEYS.list })
    },
  })
}

//--------------------------------
// THE LIVE SOCKET
//
// WHY THIS INVALIDATES RATHER THAN PREPENDING THE PUSHED EVENT DIRECTLY.
//
// The server pushes the EVENT (title, body, severity, entity) — one message
// shared by everyone it was fanned out to. A panel row is a DELIVERY: the
// event plus this user's own id and read state. The delivery id differs per
// recipient, so it is not in the shared frame, and a row synthesised from the
// push alone would have no id to mark read with — it would render and then
// fail on click.
//
// So the push is used for what it is genuinely good for — knowing something
// arrived, right now — and the authoritative row is refetched:
//
//   * the badge increments IMMEDIATELY from the frame, so the count is live
//   * the list is invalidated, so an OPEN panel refetches and the new row
//     appears at the top with a real, clickable delivery id
//   * a CLOSED panel is not fetched at all (the list query is disabled), so a
//     burst of notifications costs nothing for users who never open it
//
// Degrades to nothing if the socket never connects: the badge still refetches
// on focus, the panel still loads on open. The socket only makes it prompt.
//--------------------------------

export function useNotificationSocket() {
  const queryClient = useQueryClient()
  const [connected, setConnected] = useState(false)

  // Held in a ref so the effect below depends on nothing that changes between
  // renders — re-running it would tear down and rebuild the socket, which at
  // worst reconnect-loops for the life of the page.
  const clientRef = useRef(queryClient)
  clientRef.current = queryClient

  useEffect(() => {
    const unsubscribe = subscribeToNotifications(
      () => {
        const client = clientRef.current
        client.setQueryData<number>(NOTIFICATION_KEYS.unread, (n) => (n ?? 0) + 1)
        client.invalidateQueries({ queryKey: NOTIFICATION_KEYS.list })
      },
      { onStatus: setConnected },
    )

    return unsubscribe
  }, [])

  return { connected }
}
