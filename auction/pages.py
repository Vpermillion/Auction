"""Export the synthetic catalogue as a static GitHub Pages demo."""

import argparse
import posixpath
import shutil
import tempfile
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from flask import render_template, request, session, url_for

from . import service
from .app import MN, ROOT, create_app
from .seed import seed


DEMO_MN = {
    "Browser demo": "Хөтөч дээрх туршилт",
    "Try bidding": "Санал өгөх",
    "Place demo bid": "Туршилтын санал өгөх",
    "Demo bids stay in this browser.": "Туршилтын санал зөвхөн энэ хөтөч дээр хадгалагдана.",
    "Reset demo bids": "Туршилтын саналыг арилгах",
    "View a demo shop": "Жишээ дэлгүүр үзэх",
    "See how lots, seller terms and pickup details appear on a shop page.": "Бараа, худалдах нөхцөл болон хүлээн авах мэдээллийг жишээ дэлгүүрээс үзнэ үү.",
    "This browser": "Энэ хөтөч",
    "Enable JavaScript to try a demo bid.": "Туршилтын санал өгөхийн тулд JavaScript-ийг идэвхжүүлнэ үү.",
    "Sample result from a completed demo auction.": "Дууссан туршилтын дуудлага худалдааны жишээ үр дүн.",
    "Try the starting price, then bid at least one increment higher. Demo prices and results are stored in this browser.": "Эхлэх үнээр санал өгч, дараа нь үнийн алхмаар нэмэгдүүлнэ үү. Туршилтын үнэ, үр дүн энэ хөтөч дээр хадгалагдана.",
    "A demo bid near the deadline extends the countdown.": "Хаагдах хугацаа дөхөхөд өгсөн туршилтын санал хугацааг сунгана.",
    "Demo and privacy": "Туршилт ба нууцлал",
    "This catalogue uses sample shops and lots. Demo bids are saved in your browser.": "Энэ каталог жишээ дэлгүүр, барааг ашиглана. Туршилтын саналууд таны хөтөч дээр хадгалагдана.",
    "Use Reset demo bids to clear your test bids and restart the timers.": "Туршилтын саналыг арилгах товчоор саналаа арилгаж, хугацааг дахин эхлүүлнэ үү.",
}


def page_dir(path, language):
    prefix = "mn" if language == "mn" else ""
    return posixpath.join(prefix, path.strip("/")) or "."


def relative_url(target, current_language, target_language):
    parsed = urlsplit(target)
    source_dir = page_dir(request.path, current_language)
    if parsed.path.startswith("/static/"):
        relative = posixpath.relpath(parsed.path.lstrip("/"), source_dir)
    else:
        relative = posixpath.relpath(page_dir(parsed.path, target_language), source_dir) + "/"
    return urlunsplit(("", "", relative, parsed.query, parsed.fragment))


def configure_export(app, seeded_at):
    @app.context_processor
    def pages_context():
        lang = session.get("lang", "en")
        other_language = "mn" if lang == "en" else "en"

        def pages_url_for(endpoint, **values):
            return relative_url(url_for(endpoint, **values), lang, lang)

        def pages_lot(lot):
            return {
                "id": lot["id"],
                "start": lot["start_price"],
                "increment": lot["increment"],
                "seconds": lot["closes_at"] - seeded_at,
                "softClose": lot["soft_close"],
                "initialState": lot["state"],
            }

        def translate(label):
            return DEMO_MN.get(label, MN.get(label, label)) if lang == "mn" else label

        return {
            "pages_demo": True,
            "pages_language": relative_url(request.path, lang, other_language),
            "pages_lot": pages_lot,
            "url_for": pages_url_for,
            "t": translate,
        }

    app.view_functions["policies"] = lambda: render_template("pages_terms.html")


def export(output):
    output = Path(output)
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("The export path must be a new or empty directory.")

    with tempfile.TemporaryDirectory(prefix="auction-pages-") as temporary:
        database = Path(temporary) / "seed.sqlite3"
        service.migrate(database)
        with closing(service.connect(database)) as db:
            seed(db)
            seeded_at = db.execute("SELECT min(created_at) FROM users").fetchone()[0]
            paths = ["/", "/explore", "/policies"]
            paths += [f"/shops/{row['slug']}" for row in db.execute("SELECT slug FROM shops ORDER BY id")]
            paths += [f"/auctions/{row['id']}" for row in db.execute("SELECT id FROM auctions ORDER BY id")]

        app = create_app({"TESTING": True, "DATABASE": str(database), "SESSION_COOKIE_SECURE": False})
        configure_export(app, seeded_at)
        client = app.test_client()
        for language in ("en", "mn"):
            with client.session_transaction() as browser:
                browser["lang"] = language
            for path in paths:
                response = client.get(path)
                if response.status_code != 200:
                    raise RuntimeError(f"Could not render {path} ({response.status_code})")
                destination = output / page_dir(path, language) / "index.html"
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(response.data)

    static = ROOT / "static"
    assets = [static / name for name in ("style.css", "motion.css", "motion.js", "pages-demo.js", "images/auction-gallery.webp")]
    assets.extend((static / "fonts").iterdir())
    assets.extend((static / "images").glob("catalogue-*.jpg"))
    for source in assets:
        if source.is_file():
            destination = output / "static" / source.relative_to(static)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
    (output / ".nojekyll").touch()
    print(f"Exported {2 * len(paths)} pages to {output}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    export(parser.parse_args().output)
