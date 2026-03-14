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
  try {
    fs.accessSync(DB_PATH, fs.constants.R_OK);
    return true;
  } catch {
    return false;
  }
}
