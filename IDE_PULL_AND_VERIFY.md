# IDE Pull + Verify — FINAL consolidated package (run inside the Workshop IDE terminal)

No SSH/SSM/keys needed. The package is staged in the participant-sanctioned
`team-evidence-*` S3 namespace; the IDE's own AWS credentials pull it.
Transport integrity is verified against the `.sha256` sidecar uploaded next to the tarball.

## 0. Variables

```bash
PKG=haiec-package-final-7a0bb5f3.tar.gz
SHA=<see .sha256 sidecar>
cd ~
```

## 1. Pull + verify transport integrity

```bash
aws s3 cp s3://team-evidence-352826992186/handover/$PKG .
aws s3 cp s3://team-evidence-352826992186/handover/$PKG.sha256 .
sha256sum -c $PKG.sha256
# expected: "$PKG: OK"
```

## 2. Extract to a NEW verification dir + verify payload manifest BEFORE installing

```bash
rm -rf ~/handin-verify-7a0bb5f3 && mkdir -p ~/handin-verify-7a0bb5f3
tar -xzf $PKG -C ~/handin-verify-7a0bb5f3
cd ~/handin-verify-7a0bb5f3 && sha256sum -c MANIFEST.sha256 | grep -v ': OK$'
# expected: NO output — all 506 payload files OK
```

For the full hardened install block (traversal check, Explorer view, LogSense
install, UI/API start) use `IDE_PULL_AND_VERIFY_FINAL.md` from the handover
root — it supersedes this file.
