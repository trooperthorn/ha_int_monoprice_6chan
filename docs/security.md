# Release supply-chain controls

`.github/workflows/release.yml` runs only on a push to `main`, after the same
gate that runs on every pull request (`test.yml` and `validate.yml`, invoked
via `workflow_call`). `security.yml` adds CodeQL and Bandit on every push and
weekly; each of those jobs is a required status check on `main`.

## SBOM and attestation

| Control | Mechanism | Enforced or cosmetic |
| --- | --- | --- |
| Software bill of materials | `anchore/sbom-action`, pinned to the commit behind v0.24.2, generates an SPDX SBOM for the release archive | Enforced: the SBOM is a release asset and is attested below |
| Build provenance attestation | `actions/attest`, pinned to the commit behind v4, attests both the release archive and the SBOM | Enforced: verifiable with `gh attestation verify` |
| Action pinning | Both actions are pinned to an immutable commit SHA, not a mutable tag | Enforced against tag-hijacking supply-chain attacks |

## Immutable release sequencing

GitHub locks a release's tag and assets once published. The workflow
therefore stages a draft release, attaches every asset (archive, SBOM,
checksums), and only then flips the release to published. If a run fails
partway through, the next run finds the existing draft and resumes it
instead of starting over or leaving a broken partial release live.

## Verification

The workflow prints these commands to the run summary after a successful
release:

```bash
gh release download <tag> -R <repo> -p monoprice_custom.zip -p SHA256SUMS
sha256sum --check SHA256SUMS --ignore-missing
gh attestation verify monoprice_custom.zip -R <repo>
```
