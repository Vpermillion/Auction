import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from auction.pages import export


class PageLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        self.links.extend(value for name, value in attrs if name in ("href", "src") and value)


class PagesTest(unittest.TestCase):
    def test_project_site_links_and_demo_isolation(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "Auction"
            export(output)
            self.assertTrue((output / ".nojekyll").is_file())
            self.assertTrue((output / "mn/auctions/1/index.html").is_file())
            self.assertFalse((output / "static/app.js").exists())

            for page in output.rglob("*.html"):
                document = page.read_text()
                self.assertNotIn('name="csrf-token"', document)
                self.assertNotIn('method="post"', document)
                links = PageLinks()
                links.feed(document)
                url = "https://preview.github.io/Auction/" + page.relative_to(output).as_posix()
                for link in links.links:
                    target = urlsplit(urljoin(url, link))
                    self.assertEqual(target.netloc, "preview.github.io", link)
                    self.assertTrue(target.path.startswith("/Auction/"), (page, link))
                    asset = output / target.path.removeprefix("/Auction/")
                    if asset.is_dir():
                        asset /= "index.html"
                    self.assertTrue(asset.is_file(), (page, link))
