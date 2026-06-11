# ExportFlow — deploy notes

Target: self-hosted bench (Frappe/ERPNext v16). The app serves its React UI at
`/exportflow` via Frappe (Raven pattern) — no separate hosting, no CORS, no
nginx changes.

## Fresh install

```bash
cd /path/to/frappe-bench
bench get-app exportflow <repo-url>        # or copy into apps/ and: bench setup requirements
bench --site <site> install-app exportflow # syncs doctypes + fixtures
cd apps/exportflow/frontend
npm install && npm run build               # builds the SPA into exportflow/public/frontend
cd /path/to/frappe-bench
bench --site <site> migrate
bench build --app exportflow               # links assets
```

## Update cycle

```bash
bench --site <site> migrate     # when doctypes / fixtures / patches change
cd apps/exportflow/frontend && npm run build   # when the React app changes
```

Reload the workers afterwards. On this host `bench restart` is a no-op — use:

```bash
pkill -HUP -f "gunicorn.*frappe"
```

## Host-specific gotchas (dev server 187.127.132.58)

- Keep `exportflow` listed in `sites/apps.txt`; watch `bench migrate` output for
  "Deleting orphaned…" lines (developer_mode is on — orphan pruning deletes
  source files).
- Git remotes must use SSH (`git@github.com:…`), not HTTPS.
- The bench is multi-tenant (6 sites) — `bench build` touches all sites' assets.
