/**
 * useMomentFeedback — thin wrapper around useChat for moment feedback.
 *
 * No done_marker (only user can end), user sends the first message.
 */

import { useChat } from "./useChat";

export function useMomentFeedback(slug: string) {
  return useChat({ apiPrefix: `/api/moments/${slug}/feedback` });
}
