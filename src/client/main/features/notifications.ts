/** Check if macOS notification history DB is readable (requires Full Disk Access). */

import { canUseConnector } from "../connectors/permissions";

export function canReadNotifications(): boolean {
  return canUseConnector("notifications");
}
