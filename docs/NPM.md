# npm Package

AppAutoAction is packaged for npm as `@lazyingart/app-auto-action`.

## Install

```bash
npm install -g @lazyingart/app-auto-action
app-auto-action --version
app-auto-action webapp start --port 19473
```

The npm package is a thin Node wrapper around the bundled Python source. It requires Python 3.10+ on `PATH`; set `APPAUTOACTION_PYTHON=/path/to/python` if needed.

## Package Checks

```bash
npm test
npm run pack:dry-run
npm pack
```

The package includes the Python source, static web assets, examples, docs, bridges, configs, localized READMEs, and CLI wrappers. It excludes local outputs, `.env`, `.npmrc`, logs, caches, and generated tarballs.

## Publish

Prefer GitHub Actions trusted publishing once npm trust is configured for this repository. The workflow is `.github/workflows/npm-publish.yml` and publishes with provenance.

Trusted Publisher settings on npm:

- Package: `@lazyingart/app-auto-action`
- Publisher: GitHub Actions
- Repository: `lachlanchen/AppAutoAction`
- Workflow filename: `npm-publish.yml`
- Environment: blank, unless a GitHub deployment environment is added later

Equivalent setup command:

```bash
npm install -g npm@^11.5.1
npm trust github @lazyingart/app-auto-action --repo lachlanchen/AppAutoAction --file npm-publish.yml
```

For local bootstrap publishing, use a temporary npm config generated from an uncommitted env file:

```bash
APPAUTOACTION_NPM_ENV=../Agent/AgInTiFlow/.env npm run publish:env:whoami
APPAUTOACTION_NPM_ENV=../Agent/AgInTiFlow/.env npm run publish:env
```

`APPAUTOACTION_NPM_ENV` can also point to `../AAPS/.env` when that file contains `NPM_TOKEN` or `NODE_AUTH_TOKEN`. The helper writes a temporary `.npmrc`, runs npm, and deletes the credential material. Never commit npm tokens, `.env`, `.npmrc`, OTPs, or debug logs.
