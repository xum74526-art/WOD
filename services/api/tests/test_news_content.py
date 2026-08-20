from app.news_service import dedupe_article_images, plain_text, remove_leading_feed_excerpt, remove_trailing_source_link, sanitize_article_html


def test_news_html_is_sanitized_and_duplicate_images_are_removed():
    source = (
        '<script>alert(1)</script>'
        '<img src="/cover.png"><p>Hello &amp; GPU</p>'
        '<img src="https://example.com/cover.png">'
    )
    content = sanitize_article_html(source, "https://example.com/article")

    assert "script" not in content
    assert content.count("cover.png") == 1
    assert plain_text(content) == "Hello & GPU"


def test_dedupe_article_images_keeps_distinct_sources():
    content = '<img src="https://a.test/one.png"><img src="https://a.test/two.png"><img src="https://a.test/one.png">'
    result = dedupe_article_images(content)

    assert result.count("one.png") == 1
    assert result.count("two.png") == 1


def test_repeated_rss_excerpt_after_cover_is_removed():
    summary = "A clean article summary..."
    content = '<img src="https://a.test/cover.png">A clean article summary...<p>A clean article summary followed by the full body.</p>'
    result = remove_leading_feed_excerpt(content, summary)

    assert result == '<img src="https://a.test/cover.png"><p>A clean article summary followed by the full body.</p>'


def test_trailing_rss_source_link_is_removed():
    content = '<p>Article body.</p><p><a href="https://example.com/article">Source</a></p>'

    assert remove_trailing_source_link(content) == '<p>Article body.</p>'
