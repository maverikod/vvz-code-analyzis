"""Print the contents of the project bootstrap template zip archive."""

import zipfile

zip_path = "/home/vasilyvz/projects/tools/code_analysis/rules_template_agents_protocols_updated.zip"
with zipfile.ZipFile(zip_path) as z:
    for name in z.namelist():
        info = z.getinfo(name)
        print(f"SIZE={info.file_size} {name}")
        if not name.endswith("/"):
            try:
                content = z.read(name).decode("utf-8", errors="replace")
                print("=CONTENT_START=")
                print(content)
                print("=CONTENT_END=")
            except Exception as e:
                print(f"[error: {e}]")
