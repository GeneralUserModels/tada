/** Google OAuth 2.0 flow for Electron using a loopback redirect and system browser. */

import * as http from "http";
import { net, shell } from "electron";

export interface GoogleUser {
  name: string;
  email: string;
  googleId: string;
}

export async function startGoogleLogin(
  clientId: string,
  clientSecret: string,
): Promise<GoogleUser> {
  return new Promise((resolve, reject) => {
    const server = http.createServer();

    server.listen(0, "127.0.0.1", () => {
      const port = (server.address() as { port: number }).port;
      const redirectUri = `http://localhost:${port}`;

      const authUrl = new URL("https://accounts.google.com/o/oauth2/v2/auth");
      authUrl.searchParams.set("client_id", clientId);
      authUrl.searchParams.set("redirect_uri", redirectUri);
      authUrl.searchParams.set("response_type", "code");
      authUrl.searchParams.set("scope", "openid email profile");

      let settled = false;

      // Time out after 2 minutes if user doesn't complete login
      const timeout = setTimeout(() => {
        server.close();
        if (!settled) {
          settled = true;
          reject(new Error("Login timed out"));
        }
      }, 120_000);

      server.on("request", async (req, res) => {
        const url = new URL(req.url!, `http://localhost:${port}`);
        // Ignore non-callback requests (e.g. favicon.ico)
        if (url.pathname !== "/") {
          res.writeHead(404);
          res.end();
          return;
        }

        const code = url.searchParams.get("code");
        const error = url.searchParams.get("error");

        if (error) {
          res.writeHead(200, { "Content-Type": "text/html" });
          res.end("<html><body><h3>Login failed. You can close this tab.</h3></body></html>");
          clearTimeout(timeout);
          server.close();
          if (!settled) {
            settled = true;
            reject(new Error(error));
          }
          return;
        }

        if (!code) {
          res.writeHead(400);
          res.end();
          return;
        }

        res.writeHead(200, { "Content-Type": "text/html" });
        res.end("<html><body><h3>Signed in! You can close this tab.</h3></body></html>");

        try {
          const tokenBody = new URLSearchParams({
            code,
            client_id: clientId,
            client_secret: clientSecret,
            redirect_uri: redirectUri,
            grant_type: "authorization_code",
          });

          const tokenRes = await net.fetch("https://oauth2.googleapis.com/token", {
            method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded" },
            body: tokenBody.toString(),
          });

          if (!tokenRes.ok) {
            throw new Error(`Token exchange failed: ${tokenRes.status}`);
          }

          const tokenData = (await tokenRes.json()) as { id_token: string };
          const payload = JSON.parse(
            Buffer.from(tokenData.id_token.split(".")[1], "base64").toString("utf-8"),
          ) as { sub: string; name: string; email: string };

          clearTimeout(timeout);
          server.close();
          if (!settled) {
            settled = true;
            resolve({
              name: payload.name,
              email: payload.email,
              googleId: payload.sub,
            });
          }
        } catch (err) {
          clearTimeout(timeout);
          server.close();
          if (!settled) {
            settled = true;
            reject(err);
          }
        }
      });

      shell.openExternal(authUrl.toString());
    });
  });
}
