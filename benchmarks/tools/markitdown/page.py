import json
import re
import sys  # 127.0.0.1-only

from markitdown import MarkItDown

text = MarkItDown().convert(sys.argv[1]).markdown
pattern = r"### (?P<name>.+)\n\n\*\*Capital:\*\* (?P<capital>.+)\n\*\*Population:\*\* (?P<population>\d+)\n\*\*Area \(km2\):\*\* (?P<area_km2>\S+)"
records = [m.groupdict() for m in re.finditer(pattern, text)]
for r in records:
    r["capital"] = None if r["capital"] == "None" else r["capital"]
    r.update(population=int(r["population"]), area_km2=float(r["area_km2"]))
print(json.dumps(records))
