# code-analysis-client — examples manual (index)

PyPI does not ship a **man(1)** tree for this package. The **long-form operator
documentation** lives in the **module docstrings** of the Python files in this
directory. Treat them like manual pages: **NAME**, **SYNOPSIS**,
**DESCRIPTION**, **PREREQUISITES**, **EXIT STATUS**, **SEE ALSO**, **BUGS**,
etc.

## Reading the “man pages” without a browser

From the repository root, print the long manual embedded in
`client/examples/run_all_examples.py` (everything between the first `r"""` and
the closing `"""` of the module docstring):

```bash
python3 <<'PY'
from pathlib import Path
text = Path("client/examples/run_all_examples.py").read_text(encoding="utf-8")
i = text.find('r"""')
if i == -1:
    raise SystemExit("no r\"\"\" docstring found")
i += 4
j = text.find('"""', i)
print(text[i:j])
PY
```

Or open the `.py` files in an editor: the first triple-quoted string after the
shebang is the manual.

## Quick-start commands

```bash
cd /path/to/code_analysis_repository
source .venv/bin/activate
casmgr --config config.json start    # if not already running
python client/examples/run_all_examples.py
```

Optional:

```bash
export CODE_ANALYSIS_CONFIG=/abs/path/to/config.json
```

## Catalogue of manual pages (files)

| File | Role |
|------|------|
| `_common.py` | **CONVENTIONS** — `sys.path`, `chdir`, `CODE_ANALYSIS_CONFIG`. |
| `run_all_examples.py` | **FULL MANUAL** — every exported API + representative `JsonRpcClient` usage. |
| `ex_config_only.py` | **CONFIG(5)**-style — parse `config.json` without TCP. |
| `ex_minimal_validated.py` | **MINIMAL ASYNC(7)** — smallest validated call. |

`run_all_examples.py` exits **0** only if every assertion against the live
server succeeds.

## Relationship to the installable package

The `code_analysis_client` package is under `../` (`client/`). These examples
are **not** installed into `site-packages` by default; they live in the source
tree for operators and for PyPI users who read the sdist on GitHub or extract
the tarball.
