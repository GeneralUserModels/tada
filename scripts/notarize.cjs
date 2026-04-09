const { notarize } = require("@electron/notarize");
const dotenv = require("dotenv");
const path = require("path");

// Local releases can source APPLE_* credentials from repo env files.
dotenv.config({ path: path.resolve(__dirname, "..", ".env.local") });
dotenv.config({ path: path.resolve(__dirname, "..", ".env") });

exports.default = async function notarizing(context) {
  if (context.electronPlatformName !== "darwin") return;

  const requireNotarization = process.env.REQUIRE_NOTARIZATION === "1";

  // Skip only for non-release local builds.
  if (!process.env.APPLE_ID) {
    if (requireNotarization) {
      throw new Error(
        "[notarize] Missing APPLE_ID. Set APPLE_ID, APPLE_APP_SPECIFIC_PASSWORD, and APPLE_TEAM_ID."
      );
    }
    console.log("[notarize] Skipping — APPLE_ID not set");
    return;
  }
  if (!process.env.APPLE_APP_SPECIFIC_PASSWORD || !process.env.APPLE_TEAM_ID) {
    throw new Error(
      "[notarize] Missing APPLE_APP_SPECIFIC_PASSWORD or APPLE_TEAM_ID."
    );
  }

  const appName = context.packager.appInfo.productFilename;
  const appPath = `${context.appOutDir}/${appName}.app`;

  console.log(`[notarize] Notarizing ${appPath}...`);

  await notarize({
    tool: "notarytool",
    appPath,
    appleId: process.env.APPLE_ID,
    appleIdPassword: process.env.APPLE_APP_SPECIFIC_PASSWORD,
    teamId: process.env.APPLE_TEAM_ID,
  });

  console.log("[notarize] Done.");
};
