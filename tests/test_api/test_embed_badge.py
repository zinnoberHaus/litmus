"""Badge distribution polish — task #55.

Exhaustive coverage for:
  - size variants (small / medium / large)
  - backlink wrapper (``<a xlink:href>``) + ``<title>`` + ``<desc>`` breadcrumbs
  - shields.io-style query params (``label``, ``color``, ``style``)
  - graceful fallback on invalid params (never 404, never crash)
  - OpenGraph share card at ``/embed/<token>.html`` for Slack unfurl
"""

from __future__ import annotations

import re
from textwrap import dedent

import pytest
from fastapi.testclient import TestClient

from litmus_api.embed_svg import render_badge_svg

_VALID_SPEC = dedent("""\
    Metric: Monthly Revenue
    Description: Revenue metric for badge polish test
    Owner: data@example.com

    Source: orders

    Given all records from orders table
      And status is "completed"

    When we calculate
      Then sum the amount column

    The result is "Monthly Revenue"

    Trust:
      Freshness must be less than 24 hours
""")


# ───────────────────────── unit tests on the renderer ─────────────────────────


class TestSizeVariants:
    """The UI's /badge page already renders expecting size=small|medium|large.
    Regressions here break the marketing page's visual QA grid."""

    def test_small_is_compact(self) -> None:
        svg = render_badge_svg(metric_name="Revenue", status="passed", size="small")
        # Small is the 160×20 README size — height must match.
        m = re.search(r'height="(\d+)"', svg)
        assert m and int(m.group(1)) == 20
        # Width respects the declared minimum.
        w = re.search(r'width="(\d+)"', svg)
        assert w and int(w.group(1)) >= 160

    def test_medium_is_default(self) -> None:
        svg_default = render_badge_svg(metric_name="Revenue", status="passed")
        svg_medium = render_badge_svg(
            metric_name="Revenue", status="passed", size="medium"
        )
        # First size attribute on both svgs should match (default == medium).
        assert re.search(r'height="36"', svg_default)
        assert re.search(r'height="36"', svg_medium)

    def test_large_is_hero(self) -> None:
        svg = render_badge_svg(metric_name="Revenue", status="passed", size="large")
        m = re.search(r'height="(\d+)"', svg)
        assert m and int(m.group(1)) == 60
        # Large gets the extra wordmark glyph ("⚗ litmus") — brand flourish.
        assert "⚗ litmus" in svg

    def test_aliases_are_honored(self) -> None:
        for alias in ["sm", "s", "SMALL", "Small"]:
            svg = render_badge_svg(
                metric_name="Revenue", status="passed", size=alias
            )
            assert 'height="20"' in svg

    def test_invalid_size_falls_back_to_medium(self) -> None:
        # The never-404 contract extends to query params: bogus input degrades
        # gracefully to the default size rather than raising.
        svg = render_badge_svg(
            metric_name="Revenue", status="passed", size="extra-large-please"
        )
        assert 'height="36"' in svg

    def test_trust_score_suppressed_on_small(self) -> None:
        # Compact READMEs have no room for the "· 95" suffix.
        svg = render_badge_svg(
            metric_name="Revenue", status="passed", trust_score=0.95, size="small"
        )
        assert "· 95" not in svg
        # But it shows on medium…
        svg_md = render_badge_svg(
            metric_name="Revenue", status="passed", trust_score=0.95, size="medium"
        )
        assert "· 95" in svg_md


class TestBacklinkWrapper:
    def test_wraps_in_anchor_when_url_present(self) -> None:
        svg = render_badge_svg(
            metric_name="Revenue",
            status="passed",
            metric_url="https://litmus.example.com/metrics/revenue",
        )
        assert '<a xlink:href="https://litmus.example.com/metrics/revenue"' in svg
        assert "</a></svg>" in svg

    def test_no_anchor_when_url_absent(self) -> None:
        # LITMUS_PUBLIC_URL unset in some deployments — we skip the anchor
        # rather than linking to a relative path that breaks in Notion.
        svg = render_badge_svg(metric_name="Revenue", status="passed")
        assert "xlink:href" not in svg

    def test_title_tooltip_for_attribution(self) -> None:
        svg = render_badge_svg(
            metric_name="Revenue",
            status="passed",
            metric_url="https://litmus.example.com/metrics/revenue",
        )
        assert "<title>Powered by Litmus" in svg
        # And a <desc> for stripped-embed breadcrumbs (Notion strips anchors).
        assert "<desc>" in svg
        assert "https://litmus.example.com/metrics/revenue" in svg

    def test_url_is_html_escaped(self) -> None:
        svg = render_badge_svg(
            metric_name="Revenue",
            status="passed",
            metric_url="https://example.com/?a=1&b=2",
        )
        # Ampersand must be escaped inside the anchor href attribute.
        assert "&amp;" in svg


class TestQueryParamOverrides:
    def test_label_override(self) -> None:
        svg = render_badge_svg(
            metric_name="very_long_internal_slug", status="passed", label="Revenue"
        )
        assert ">Revenue<" in svg
        # Original slug must not leak.
        assert "very_long_internal_slug" not in svg

    def test_color_override(self) -> None:
        svg = render_badge_svg(
            metric_name="Revenue", status="passed", color="4c1d95"
        )
        # Custom purple accent replaces the status-derived green.
        assert "#4c1d95" in svg
        assert "#16a34a" not in svg

    def test_invalid_color_falls_back(self) -> None:
        # "not-a-color" isn't 3/6 hex digits — we ignore it and use green.
        svg = render_badge_svg(
            metric_name="Revenue", status="passed", color="not-a-color"
        )
        assert "#16a34a" in svg

    def test_color_accepts_three_digit_hex(self) -> None:
        svg = render_badge_svg(metric_name="Revenue", status="passed", color="f00")
        assert "#f00" in svg

    def test_color_accepts_leading_hash(self) -> None:
        # Users habitually paste "#4c1d95" from a design tool — accept it.
        svg = render_badge_svg(
            metric_name="Revenue", status="passed", color="#4c1d95"
        )
        assert "#4c1d95" in svg

    def test_style_for_the_badge(self) -> None:
        svg = render_badge_svg(
            metric_name="Revenue", status="passed", style="for-the-badge"
        )
        # Upper-case shields.io look.
        assert ">LITMUS<" in svg
        assert ">TRUSTED<" in svg

    def test_style_flat_is_default(self) -> None:
        svg = render_badge_svg(metric_name="Revenue", status="passed")
        # Flat layout uses the pill with two rects + dot + text — no upper-case shouting.
        assert "LITMUS" not in svg
        assert "Trusted" in svg


# ───────────────────────── integration tests on the route ─────────────────────────


class TestBadgeRouteSizeParams:
    def test_small_size_param(self, client: TestClient) -> None:
        m = client.post("/api/v1/metrics", json={"spec_text": _VALID_SPEC}).json()
        r = client.get(f"/embed/{m['embed_token']}/badge.svg?size=small")
        assert r.status_code == 200
        assert 'height="20"' in r.text

    def test_large_size_param(self, client: TestClient) -> None:
        m = client.post("/api/v1/metrics", json={"spec_text": _VALID_SPEC}).json()
        r = client.get(f"/embed/{m['embed_token']}/badge.svg?size=large")
        assert r.status_code == 200
        assert 'height="60"' in r.text

    def test_default_is_medium(self, client: TestClient) -> None:
        m = client.post("/api/v1/metrics", json={"spec_text": _VALID_SPEC}).json()
        r = client.get(f"/embed/{m['embed_token']}/badge.svg")
        assert r.status_code == 200
        assert 'height="36"' in r.text

    def test_invalid_size_falls_back(self, client: TestClient) -> None:
        m = client.post("/api/v1/metrics", json={"spec_text": _VALID_SPEC}).json()
        r = client.get(f"/embed/{m['embed_token']}/badge.svg?size=xxxl")
        assert r.status_code == 200
        assert 'height="36"' in r.text


class TestBadgeRouteCustomization:
    def test_label_override(self, client: TestClient) -> None:
        m = client.post("/api/v1/metrics", json={"spec_text": _VALID_SPEC}).json()
        r = client.get(f"/embed/{m['embed_token']}/badge.svg?label=MRR")
        assert r.status_code == 200
        assert ">MRR<" in r.text

    def test_color_override(self, client: TestClient) -> None:
        m = client.post("/api/v1/metrics", json={"spec_text": _VALID_SPEC}).json()
        r = client.get(f"/embed/{m['embed_token']}/badge.svg?color=4c1d95")
        assert r.status_code == 200
        assert "#4c1d95" in r.text

    def test_for_the_badge_style(self, client: TestClient) -> None:
        m = client.post("/api/v1/metrics", json={"spec_text": _VALID_SPEC}).json()
        r = client.get(
            f"/embed/{m['embed_token']}/badge.svg?style=for-the-badge"
        )
        assert r.status_code == 200
        assert ">LITMUS<" in r.text


class TestBadgeRouteBacklink:
    def test_backlink_present_when_public_url_configured(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LITMUS_PUBLIC_URL", "https://litmus.example.com")
        m = client.post("/api/v1/metrics", json={"spec_text": _VALID_SPEC}).json()
        r = client.get(f"/embed/{m['embed_token']}/badge.svg")
        assert r.status_code == 200
        # Backlink points at the human-readable slug URL, not the token URL.
        assert 'xlink:href="https://litmus.example.com/metrics/monthly_revenue"' in r.text

    def test_no_backlink_when_public_url_unset(self, client: TestClient) -> None:
        # Default conftest doesn't set LITMUS_PUBLIC_URL. No broken relative
        # anchor; the SVG still renders.
        m = client.post("/api/v1/metrics", json={"spec_text": _VALID_SPEC}).json()
        r = client.get(f"/embed/{m['embed_token']}/badge.svg")
        assert r.status_code == 200
        assert "xlink:href" not in r.text

    def test_title_tooltip_always_present(self, client: TestClient) -> None:
        m = client.post("/api/v1/metrics", json={"spec_text": _VALID_SPEC}).json()
        r = client.get(f"/embed/{m['embed_token']}/badge.svg")
        assert "<title>Powered by Litmus" in r.text


class TestBadgeRouteUnknownTokenResilience:
    """The never-404 contract: invalid tokens + params still render."""

    def test_unknown_token_with_size(self, client: TestClient) -> None:
        r = client.get("/embed/lme_definitelynotatoken/badge.svg?size=large")
        assert r.status_code == 200
        assert 'height="60"' in r.text
        assert "Unknown" in r.text

    def test_unknown_token_with_all_params(self, client: TestClient) -> None:
        r = client.get(
            "/embed/lme_nope/badge.svg"
            "?size=small&label=Offline&color=ff0000&style=flat"
        )
        assert r.status_code == 200
        assert ">Offline<" in r.text


class TestOpenGraphCard:
    """Slack (and Twitter, LinkedIn, iMessage) unfurl via og:* / twitter:* tags."""

    def test_og_card_html_served(self, client: TestClient) -> None:
        m = client.post("/api/v1/metrics", json={"spec_text": _VALID_SPEC}).json()
        r = client.get(f"/embed/{m['embed_token']}.html")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/html")

    def test_og_image_points_at_svg(self, client: TestClient) -> None:
        m = client.post("/api/v1/metrics", json={"spec_text": _VALID_SPEC}).json()
        r = client.get(f"/embed/{m['embed_token']}.html")
        assert 'property="og:image"' in r.text
        assert f"/embed/{m['embed_token']}/badge.svg" in r.text

    def test_og_tags_required_for_slack_unfurl(self, client: TestClient) -> None:
        m = client.post("/api/v1/metrics", json={"spec_text": _VALID_SPEC}).json()
        r = client.get(f"/embed/{m['embed_token']}.html")
        # Slack reads: og:title, og:description, og:image, og:url.
        for tag in ["og:title", "og:description", "og:image", "og:url"]:
            assert f'property="{tag}"' in r.text, f"Missing {tag} tag"
        # Twitter card for wider compatibility.
        assert 'name="twitter:card"' in r.text

    def test_og_card_never_404s(self, client: TestClient) -> None:
        r = client.get("/embed/lme_definitelynotatoken.html")
        assert r.status_code == 200
        assert "og:image" in r.text
