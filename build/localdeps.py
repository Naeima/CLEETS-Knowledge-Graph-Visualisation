"""Local copies of the page's web dependencies for headless work (layout baking, screenshots, tests).

The pages load d3 from cdnjs and their fonts from Google Fonts. Headless runs in a sandbox with no network
get the same files from node_modules (see package.json: `npm install` next to this file), found through
NODE_MODULES or in the usual places."""
import os, re

HERE = os.path.dirname(os.path.abspath(__file__))
_candidates = [os.environ.get("NODE_MODULES", ""), os.path.join(HERE, "node_modules"),
               os.path.join(os.path.dirname(HERE), "node_modules"), os.path.join(os.path.dirname(HERE), "fonts", "node_modules")]
NODE = next((d for d in _candidates if d and os.path.isdir(d)), os.path.join(HERE, "node_modules"))
CDN_D3 = '<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js"></script>'
FONT_LINK = re.compile(r'<link rel="stylesheet" href="https://fonts.googleapis.com[^>]*>')
SKEL_CSS = ":root{color-scheme:light}body{margin:0;font:14px system-ui,sans-serif}img{max-width:100%}[hidden]{display:none!important}"


def d3_source():
    return open(os.path.join(NODE, "d3", "dist", "d3.min.js"), encoding="utf-8").read()


def inline_d3(body):
    """Replace the cdnjs script tag with the local copy of d3 (same version)."""
    return body.replace(CDN_D3, "<script>" + d3_source().replace("</script", "<\\/script") + "</script>")


def drop_d3(body):
    return body.replace(CDN_D3, "")


def fontsource_dir():
    return os.path.join(NODE, "@fontsource")


def strip_font_link(body, replacement=""):
    return FONT_LINK.sub(replacement, body)


def is_document(body):
    return body.lstrip()[:15].lower().startswith("<!doctype")


def page(body, extra_css="", theme=None):
    """A complete document from either form of a built page: the artifact body (wrapped in the host's skeleton here)
    or a standalone document (used as is, with the theme attribute and extra CSS injected)."""
    attr = f' data-theme="{theme}"' if theme else ""
    if is_document(body):
        doc = body.replace("<html lang=\"en\">", f"<html lang=\"en\"{attr}>", 1)
        return doc.replace("</head>", f"<style>{extra_css}</style></head>", 1) if extra_css else doc
    return (f'<!doctype html><html{attr}><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
            f"<style>{SKEL_CSS}{extra_css}</style></head><body>{body}</body></html>")
