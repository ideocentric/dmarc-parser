# Developer Example Data — Drop Zone

This directory is for developer use only during parser debugging and compatibility testing. It is **not** part of the automated functional test flow.

## Structure

```
example-data/
├── acme-test/     Place real DMARC report files here to test against acme-test client
└── globex-test/   Place real DMARC report files here to test against globex-test client
```

## Usage

Drop `.xml.gz` or `.zip` DMARC aggregate report files into the appropriate subdirectory, then copy them to the platform's incoming folder:

```bash
cp example-data/acme-test/*.xml.gz \
   docker-data/reports/incoming/acme-test/
```

Or use the `mgr scan` command after copying:

```bash
mgr scan acme-test
```

## Notes

- Files inside these subdirectories are git-ignored — only this README and the `.gitkeep` placeholders are committed.
- For automated functional testing, use `tests/generate_sample_data.py` instead.
- Real-world files placed here may contain actual company names — do not use them in demos or screenshots intended for external audiences.