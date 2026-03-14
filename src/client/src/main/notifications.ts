/** Check if macOS notification history DB is readable. */

import * as path from "path";
import * as os from "os";
import * as fs from "fs";

const DB_PATH = path.join(
  os.homedir(),
  "Library", "Group Containers",
  "group.com.apple.usernoted", "db2", "db"
);

export function canReadNotifications(): boolean {
  // Check if the notification DB directory exists (don't check R_OK — that
  // requires Full Disk Access which may not be granted yet at onboarding time).
  try {
    const dbDir = path.dirname(DB_PATH);
    return fs.existsSync(dbDir);
  } catch {
    return false;
  }
}
