import re

from site2md.extractors.v1 import Extraction, RecordCandidate

FIELDS = re.compile(r"Capital: (.*)\nPopulation: (.*)\nArea \(km2\): (.*)")


class Countries:
    def extract(self, document):
        records = []
        for section in document.sections:
            for node in section.nodes:
                text = document.plain_text(node)
                if node.kind == "heading":
                    name = text
                elif fields := FIELDS.fullmatch(text):
                    capital, population, area = fields.groups()
                    value = {
                        "name": name,
                        "capital": None if capital == "None" else capital,
                        "population": int(population),
                        "area_km2": float(area),
                    }
                    records.append(RecordCandidate(value, (node.span,)))
        return Extraction(tuple(records))
