import re
from pathlib import Path

import pytest

from config import COOKIE_NAME
from services.auth import sign_cookie


class TestPrintSchedule:
    @pytest.fixture
    def admin_client(self, client, admin_user):
        """Клиент с авторизованной админской сессией, без использования /login."""
        client.cookies.set(COOKIE_NAME, sign_cookie(admin_user.id))
        return client

    def test_admin_print_returns_full_html_page(self, admin_client, admin_user):
        """/admin/print должен возвращать полную самостоятельную HTML-страницу."""
        response = admin_client.get("/admin/print")
        assert response.status_code == 200
        text = response.text
        assert "<!DOCTYPE html>" in text
        assert "<html" in text
        assert "Расписание смен" in text
        assert "id=\"main-content\"" not in text

    def test_spa_handler_skips_target_blank_links(self):
        """SPA-обработчик не должен перехватывать ссылки
        с target=\"_blank\" (например, кнопку печати расписания)."""
        base_html = Path("templates/base.html").read_text(encoding="utf-8")

        # Находим SPA-блок по уникальному маркеру
        spa_block_start = base_html.find("function attachLinkHandlers()")
        assert spa_block_start != -1, "SPA navigation block not found"
        spa_block = base_html[spa_block_start:]

        # Извлекаем функцию attachLinkHandlers
        match = re.search(
            r"function\s+attachLinkHandlers\(\)\s*\{(.*?)^  \}",
            spa_block,
            re.DOTALL | re.MULTILINE,
        )
        assert match, "attachLinkHandlers not found in SPA block"
        handler_body = match.group(1)

        # Должен быть guard, который пропускает target="_blank"
        assert "link.target === '_blank'" in handler_body, (
            "SPA handler does not skip target='_blank' links"
        )

    def test_admin_page_has_print_link_with_target_blank(self, admin_client, admin_user):
        """На странице /admin кнопка печати должна открываться в новой вкладке."""
        response = admin_client.get("/admin")
        assert response.status_code == 200
        text = response.text
        assert 'id="print-btn"' in text
        assert '/admin/print' in text
        assert 'target="_blank"' in text
