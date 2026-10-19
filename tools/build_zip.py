"""Build dist/ui_builder.zip, installable via Edit > Preferences > Add-ons > Install from Disk."""
import os
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "ui_builder")
OUT = os.path.join(ROOT, "dist", "ui_builder.zip")

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zf:
    for base, dirs, files in os.walk(SRC):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in sorted(files):
            path = os.path.join(base, f)
            zf.write(path, os.path.relpath(path, ROOT))
print("wrote", OUT)
