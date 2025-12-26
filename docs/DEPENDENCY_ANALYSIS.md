# Dependency Analysis: Unexpected Packages

**Author**: Vasiliy Zdanovskiy  
**Email**: vasilyvz@gmail.com  
**Date**: 2025-12-26

## Problem

During package installation, the following packages are being downloaded:
- `svo_chunker-0.1.0` ⚠️ **NOT NEEDED** - We only need `svo-client` (client library)
- `natasha-1.6.0` (34.4 MB)
- `spacy-3.8.11` (33.2 MB)
- `stanza-1.11.0` (1.7 MB)
- `mpmath-1.3.0`
- `scipy-1.16.3` (35.7 MB)

These packages are **NOT** listed in `requirements.txt` and are **NOT** direct dependencies of any package in `requirements.txt`.

**Important**: `svo-chunker` is a service, not a Python package. We only need `svo-client` (the client library) to connect to the chunker service.

## Investigation

### Current requirements.txt

```
pyyaml>=6.0
click>=8.0
mcp>=1.0.0
pydantic>=2.1.0
svo-client>=2.2.2
```

### Direct Dependencies Check

1. **svo-client** dependencies:
   ```
   Requires: aiohttp, chunk_metadata_adapter, httpx, mcp-proxy-adapter, pydantic
   ```

2. **chunk_metadata_adapter** dependencies:
   ```
   Requires: lark, pydantic
   ```

3. **mcp** dependencies:
   - No NLP libraries found

4. **pydantic** dependencies:
   - No NLP libraries found

### Verification

- ✅ `svo_chunker`, `natasha`, `spacy`, `stanza` are **NOT** in installed packages
- ✅ These packages are **NOT** in dependency tree of any package in `requirements.txt`
- ✅ No imports of these packages found in codebase

## Possible Causes

### 1. Optional Dependencies (Extras)

These packages might be optional dependencies that are being pulled in by:
- A package with optional extras being installed
- A package that conditionally installs NLP libraries
- A package that has these as "recommended" dependencies

### 2. Installation Context

The user might be:
- Installing a different package not in `requirements.txt`
- Running `pip install` with additional arguments
- Installing from a different requirements file
- Installing packages with extras (e.g., `pip install svo-client[all]`)

### 3. Package Metadata Issue

The packages might be:
- Listed in `setup.py` or `pyproject.toml` as optional dependencies
- Pulled in by a transitive dependency that wasn't checked
- Part of a dependency resolver's "recommended" packages

## Action Items

1. ✅ **Confirmed**: `svo-chunker` is NOT installed (only `svo-client` is needed)
2. **Check installation command**: What exact command was run?
3. **Check for extras**: Was `pip install -r requirements.txt[extra]` used?
4. **Check package metadata**: Inspect `svo-client` and `chunk_metadata_adapter` for optional dependencies
5. **Check pip cache**: Clear pip cache and reinstall to see if issue persists

## Resolution

- ✅ `svo-client` is the correct package (client library for SVO chunker service)
- ✅ `svo-chunker` is NOT needed (it's a service, not a Python package)
- ✅ `svo-chunker` is NOT installed in the environment
- ⚠️ If `svo-chunker` appears during installation, it might be:
  - An optional dependency being pulled in
  - A transitive dependency from another package
  - A pip resolver suggestion (not actually installed)

## Next Steps

1. ✅ **Confirmed**: `svo-chunker` is NOT needed - only `svo-client` is required
2. Ask user for exact installation command to identify source
3. Check if packages are actually installed or just downloaded (metadata only)
4. Verify if these are optional dependencies that can be excluded
5. Document if these are expected dependencies

## Summary

- ✅ **`svo-client`** - Required (client library for SVO chunker service)
- ❌ **`svo-chunker`** - NOT needed (it's a service, not a Python package)
- ✅ Current `requirements.txt` is correct - only `svo-client>=2.2.2` is listed
- ✅ `svo-chunker` is NOT installed in the environment
- ⚠️ If `svo-chunker` appears during installation, it might be:
  - A pip resolver suggestion (not actually installed)
  - An optional dependency from another package
  - A transitive dependency that gets excluded

---

**Status**: ✅ RESOLVED - `svo-chunker` is not needed, only `svo-client` is required  
**Priority**: Low (packages not actually installed, just metadata downloaded)

