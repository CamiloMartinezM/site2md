import json
import re
import subprocess
import sys  # 127.0.0.1-only

cmd = ["pandoc", "-f", "html", "-t", "gfm", sys.argv[1]]
text = subprocess.check_output(cmd, encoding="utf-8")
pattern = r'###  (?P<name>.+)\n\n<div class="country-info">\n\n\*\*Capital:\*\* <span class="country-capital">(?P<capital>.+)</span>\\\n\*\*Population:\*\* <span class="country-population">(?P<population>\d+)</span>\\\n\*\*Area \(km<sup>2</sup>\):\*\* <span class="country-area">(?P<area_km2>\S+)</span>\\'
records = [m.groupdict() for m in re.finditer(pattern, text)]
for r in records:
    r["name"] = r["name"].replace("\\", "")
    r["capital"] = None if r["capital"] == "None" else r["capital"]
    r.update(population=int(r["population"]), area_km2=float(r["area_km2"]))
print(json.dumps(records))
