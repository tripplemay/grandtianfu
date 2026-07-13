# Agent instructions

- Read `CLAUDE.md` before changing code or running tests.
- Before any production, deployment, DNS, data, or rollback work, read
  `docs/生产环境交接.md`. It is the canonical source for the current production
  topology and supersedes older host references in historical planning docs.
- Production no longer runs on `ssh kolmatrix`. Do not treat the old VPS or the
  repository's sample data as the live source of truth.
- Never place credentials in this repository. Follow the external credential
  references documented in `docs/生产环境交接.md`.
