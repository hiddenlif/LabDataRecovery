"""Compare observable data without imposing bitwise floating-point identity."""
import math
from html.parser import HTMLParser
import pytest


def equivalent(actual, expected):
    if isinstance(expected, dict):
        assert isinstance(actual, dict) and actual.keys() == expected.keys()
        for key in expected:
            equivalent(actual[key], expected[key])
    elif isinstance(expected, list):
        assert isinstance(actual, list) and len(actual) == len(expected)
        for left, right in zip(actual, expected):
            equivalent(left, right)
    elif isinstance(expected, float):
        assert isinstance(actual, (float, int)) and not isinstance(actual, bool)
        assert math.isfinite(actual)
        assert actual == pytest.approx(expected, rel=1e-9, abs=1e-10)
    else:
        assert actual == expected


class ReportText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.suppressed = 0

    def handle_starttag(self, tag, attrs):
        if tag in {'script', 'style'}:
            self.suppressed += 1

    def handle_endtag(self, tag):
        if tag in {'script', 'style'}:
            self.suppressed = max(0, self.suppressed-1)

    def handle_data(self, data):
        if not self.suppressed:
            self.parts.append(data)


def report_text(source):
    parser = ReportText()
    parser.feed(source)
    return ' '.join(parser.parts)
