"""Wrap a page body (the form the claude.ai artifact host expects: <title>, <link>, <style>, markup, <script>)
in a complete HTML document for plain web hosting such as GitHub Pages."""
import re

SKELETON = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="description" content="{description}">
{head}
<style>body{{margin:0}}img{{max-width:100%}}[hidden]{{display:none!important}}</style>
</head>
<body>
{body}
</body>
</html>
"""


def wrap(body, description):
    head = []
    for pattern in (r"<title>.*?</title>", r'<link rel="stylesheet"[^>]*>', r"<style>.*?</style>"):
        m = re.search(pattern, body, re.S)
        if not m:
            continue
        head.append(m.group(0))
        body = body[:m.start()] + body[m.end():]
    return SKELETON.format(description=description.replace('"', "&quot;"), head="\n".join(head), body=body.strip())
