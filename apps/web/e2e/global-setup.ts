import { spawnSync } from "node:child_process";
import { resolve } from "node:path";

export default function globalSetup() {
  const backendDir = resolve(__dirname, "../../backend");
  const python = process.env.KAI_BACKEND_PYTHON ?? resolve(
    backendDir,
    process.platform === "win32" ? ".venv313/Scripts/python.exe" : ".venv313/bin/python",
  );
  const result = spawnSync(
    python,
    ["-m", "app.dev_seed", "--confirm-local", "--json"],
    {
      cwd: backendDir,
      encoding: "utf8",
      env: { ...process.env, NEWS_SYNC_ENABLED: "false" },
    },
  );
  if (result.status !== 0) {
    throw new Error(`Development seed failed:\n${result.stderr || result.stdout}`);
  }
}
