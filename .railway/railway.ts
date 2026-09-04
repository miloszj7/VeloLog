import { defineRailway, github, preserve, project, service, volume } from "railway/iac";

export default defineRailway(() => {
  const velologVolume = volume("velolog-volume", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: "ams", sizeMB: 500 });
  const VeloLog = service("VeloLog", {
    source: github("miloszj7/VeloLog"),
    start: "uv run python manage.py collectstatic --noinput && uv run python manage.py migrate && uv run gunicorn velo_log.wsgi --bind 0.0.0.0:$PORT",
    replicas: { "ams": 1 },
    networking: { privateNetworkEndpoint: "velolog" },
    volumeMounts: { "/data": velologVolume },
    env: { ALLOWED_HOSTS: preserve(), DB_PATH: preserve(), DEBUG: preserve(), MEDIA_ROOT: preserve(), RAILPACK_PYTHON_VERSION: preserve(), RAILWAY_RUN_UID: preserve(), SECRET_KEY: preserve() },
  });

  return project("velolog", {
    resources: [VeloLog, velologVolume],
  });
});
