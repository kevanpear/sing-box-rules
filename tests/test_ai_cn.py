#!/usr/bin/env python3.11
"""Regressions for the narrow domain exception and foreign-provider boundary."""
import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check_ai_cn.py"
spec = importlib.util.spec_from_file_location("china_ai_rules", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads(module.SOURCE.read_text())

    def load(self, catalog):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "providers.json"
            path.write_text(json.dumps(catalog))
            return module.load_ruleset(path)

    def test_official_endpoints_and_boundary(self):
        rules = self.load(self.catalog)["rules"]

        def allowed(host):
            return any(module.matches(host, domain, kind == "domain_suffix")
                       for rule in rules for kind, domains in rule.items() for domain in domains)

        for host in (
            "api.deepseek.com", "ark.cn-beijing.volces.com", "api.kimi.com",
            "auth.kimi.com", "code.kimi.com", "code-rc.kimi.com", "cdn.kimi.com",
            "telemetry-logs.kimi.com", "api.moonshot.cn", "api.kimi.ai",
            "api.xiaomimimo.com", "token-plan-cn.xiaomimimo.com",
            "token-plan-sgp.xiaomimimo.com", "id.mi.com", "account.xiaomi.com",
        ):
            self.assertTrue(allowed(host), host)
        for host in (*module.PROTECTED, "api.anthropic.com", "api.openai.com",
                     "kimi.com.example.com", "notkimi.com", "foo.volces.com",
                     "www.xiaomi.com", "foo.aliyuncs.com", "192.0.2.1"):
            self.assertFalse(allowed(host), host)

    def test_rejects_broad_mistyped_or_protected_entries(self):
        for kind, host in (
            ("domain_suffix", "com"), ("domain_suffix", "mi.com"),
            ("domain_suffix", "volces.com"), ("domain_suffix", "anthropic.com"),
            ("domain", "api.openai.com"), ("domain", "https://api.kimi.com"),
            ("domain", "*.kimi.com"), ("domain", "KIMI.COM"),
            ("domain", "192.0.2.1"), ("domain_suffix", ".kimi.com"),
        ):
            with self.subTest(kind=kind, host=host):
                catalog = copy.deepcopy(self.catalog)
                catalog["rules"].append({kind: [host]})
                with self.assertRaises(ValueError):
                    self.load(catalog)

    def test_rejects_overlaps_and_unknown_fields(self):
        for change in ({"domain": ["api.kimi.com"]}, {"domain_keyword": ["kimi"]}):
            catalog = copy.deepcopy(self.catalog)
            catalog["rules"][0].update(change)
            with self.assertRaises(ValueError):
                self.load(catalog)

    def test_direct_classification_and_upstream_exclusion(self):
        shared = importlib.util.spec_from_file_location("shared_rulesets", SCRIPT.parent / "rulesets.py")
        definitions = importlib.util.module_from_spec(shared)
        shared.loader.exec_module(definitions)
        self.assertIn("geosite_ai_cn", definitions.NON_PROXY)
        self.assertIn("geosite_ai_cn", definitions.DIRECT_LIKE)
        self.assertNotIn("geosite_ai_cn", {p.stem for p in definitions.fine_proxy_rulesets()})
        terms = {host for rule in self.catalog["rules"] for hosts in rule.values() for host in hosts}
        self.assertTrue(terms <= definitions.direct_like_terms())


if __name__ == "__main__":
    unittest.main()
