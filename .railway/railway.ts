import { defineRailway, project, service } from "railway/iac";

// Last resort for a per-service CaC repo. Prefer one .railway file for the
// project and drop this if you later combine services into that file.
export const partial = "VeloLog";

export default defineRailway(() => {
  const VeloLog = service("VeloLog", {
    start: "uv run python manage.py collectstatic --noinput && uv run python manage.py migrate && uv run gunicorn velo_log.wsgi --bind 0.0.0.0:$PORT",
  });
  return project("diligent-charm", {
    resources: [VeloLog],
  });
});
