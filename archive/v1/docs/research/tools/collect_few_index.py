"""Save public bibliographic metadata, not copyrighted article bodies."""

import csv
import json
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1] / "indexes"
BASE = "https://www.perceptualedge.com/"


class IndexParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.section = ""
        self.in_heading = False
        self.href = None
        self.label = ""
        self.rows = []

    def handle_starttag(self, tag, attrs):
        if tag == "h2":
            self.in_heading = True
            self.section = ""
        if tag == "a":
            self.href = dict(attrs).get("href")
            self.label = ""

    def handle_data(self, data):
        if self.in_heading:
            self.section += data
        if self.href:
            self.label += data

    def handle_endtag(self, tag):
        if tag == "h2":
            self.in_heading = False
        if tag == "a" and self.href:
            href = self.href
            if not href.startswith("#") and self.section and self.label.strip():
                self.rows.append(
                    {"topic": self.section.strip(), "title": self.label.strip(), "url": urljoin(BASE, href)}
                )
            self.href = None


def main():
    parser = IndexParser()
    with urlopen(BASE + "article-index.php", timeout=30) as response:
        parser.feed(response.read().decode())
    rows = list({(r["topic"], r["url"]): r for r in parser.rows}.values())
    with (ROOT / "stephen-few-public.csv").open("w") as f:
        writer = csv.DictWriter(f, fieldnames=["topic", "title", "url"])
        writer.writeheader()
        writer.writerows(rows)
    topics = [
        "Data visualization techniques and best practices",
        "Specific chart types",
        "Visual exploratory data analysis",
        "Data visualization concepts and taxonomies",
        "Principles of design",
        "Perception and cognition",
        "Self-Service Analytics",
    ]
    related = [r for r in rows if r["topic"] in topics]
    (ROOT / "stephen-few-relevant.json").write_text(json.dumps(related, indent=2))
    print(
        json.dumps(
            {
                "topic_entries": len(rows),
                "unique_urls": len({r["url"] for r in rows}),
                "related_entries": len(related),
                "topics": sorted({r["topic"] for r in rows}),
            },
            indent=2,
        )
    )
    for r in related:
        print(r["title"], "|", r["url"])


if __name__ == "__main__":
    main()
