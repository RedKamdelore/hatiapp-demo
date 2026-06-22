import re
import pytest
import models


def _input_value(html, input_id):
    pattern = re.compile(rf'<input[^>]*id="{re.escape(input_id)}"[^>]*>', re.IGNORECASE)
    match = pattern.search(html)
    assert match, f"input #{input_id} not found"
    value_match = re.search(r'value="([^"]*)"', match.group(0), re.IGNORECASE)
    return value_match.group(1) if value_match else ""


def _selected_option(html, select_id):
    pattern = re.compile(rf'<select[^>]*id="{re.escape(select_id)}"[^>]*>(.*?)</select>', re.IGNORECASE | re.DOTALL)
    match = pattern.search(html)
    assert match, f"select #{select_id} not found"
    selected = re.search(r'<option[^>]*selected[^>]*value="([^"]*)"', match.group(1), re.IGNORECASE)
    if not selected:
        selected = re.search(r'<option[^>]*value="([^"]*)"[^>]*selected', match.group(1), re.IGNORECASE)
    return selected.group(1) if selected else ""


def test_admin_page_preserves_filter_params(client, admin_with_session, db):
    direction = models.Direction(name="Filter Direction")
    db.add(direction)
    db.commit()
    db.refresh(direction)

    try:
        response = client.get(f"/admin?q=ivan&role=volunteer&status=active&direction={direction.id}&sort=name_asc")
        assert response.status_code == 200
        html = response.text
        assert "filter-role" in html
        assert "filter-status" in html
        assert "filter-direction" in html

        assert _input_value(html, "user-search") == "ivan"
        assert _selected_option(html, "filter-role") == "volunteer"
        assert _selected_option(html, "filter-status") == "active"
        assert _selected_option(html, "filter-direction") == str(direction.id)
    finally:
        db.delete(direction)
        db.commit()


def test_admin_page_sort_links_preserve_filters(client, admin_with_session):
    response = client.get("/admin?q=ivan&role=volunteer")
    assert response.status_code == 200
    html = response.text

    sort_links = re.findall(r'<a[^>]*class="[^"]*sort-link[^"]*"[^>]*href="([^"]*)"', html, re.IGNORECASE)
    if not sort_links:
        sort_links = re.findall(r'<a[^>]*href="([^"]*)"[^>]*class="[^"]*sort-link[^"]*"', html, re.IGNORECASE)
    assert sort_links, "no sort links found"
    assert any("q=ivan" in href and "role=volunteer" in href for href in sort_links), (
        "no sort link preserves both q=ivan and role=volunteer"
    )
