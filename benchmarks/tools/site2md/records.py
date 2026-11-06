import json
from pathlib import Path

result = json.loads(Path("result.json").read_text(encoding="utf-8"))
print(json.dumps([record["value"] for record in result["records"]]))
