"""Test navigateur (Selenium + Chrome) : les vues du tableau de bord ne defilent jamais horizontalement.

Lent (quelques minutes) : ignore par defaut. Pour l'executer :  RUN_BROWSER_TESTS=1 python -m pytest tests/browser -q
"""
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

pytestmark = pytest.mark.skipif(os.environ.get("RUN_BROWSER_TESTS") != "1", reason="test navigateur : definir RUN_BROWSER_TESTS=1")

PAGES = ["/index.html", "/assignments-completed.html", "/restitutions-pending.html", "/restitutions-completed.html"]
WIDTHS = [768, 900, 1024, 1100, 1280, 1366, 1920]
JS = """
var wrap = document.querySelector('.table-responsive');
return {page: [document.documentElement.scrollWidth, document.documentElement.clientWidth],
        wrap: wrap ? [wrap.scrollWidth, wrap.clientWidth] : [0, 0]};
"""


def test_dashboard_views_never_scroll_horizontally():
    pytest.importorskip("selenium")
    from browser_harness import Instance
    problems = []
    with Instance(copy_db="backend/dotation.db") as inst:
        for width in WIDTHS:
            driver = inst.driver(width=width)
            for page in PAGES:
                driver.get(inst.url(page))
                time.sleep(2)
                result = driver.execute_script(JS)
                if result["page"][0] > result["page"][1] + 1 or result["wrap"][0] > result["wrap"][1] + 1:
                    problems.append(f"{width}px {page} : page={result['page']} tableau={result['wrap']}")
            driver.quit()
    assert problems == []
