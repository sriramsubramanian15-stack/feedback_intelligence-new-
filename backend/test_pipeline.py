"""Offline regression checks. No API credentials or paid requests are used."""
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from analytics import read_feedback, build_result
from main import app
import json

SETTINGS = {"company": "Acme Shop", "context": "Online shopping with payments and account settings.",
            "rules": [{"id": "payments", "label": "Payment problems", "phrases": ["payment failed"], "priority": "high"},
                      {"id": "ui", "label": "UI improvements", "phrases": ["confusing menu"], "priority": "low"}]}
RAW = (Path(__file__).parent.parent / "sample-feedback.csv").read_bytes()


def fake_ai(rows, *_):
    # Fixed classifier fixture, not a replacement AI or keyword fallback.
    classified = {1: ("matched", ["payments"]), 3: ("matched", ["payments"]),
                  4: ("matched", ["payments"]), 5: ("matched", ["ui"]),
                  6: ("matched", ["ui"]), 7: ("matched", ["ui"]),
                  8: ("irrelevant", []), 9: ("needs_review", []),
                  10: ("no_action", []), 11: ("matched", ["payments", "ui"])}
    return [{"id": r["id"], "status": classified[r["id"]][0],
             "rule_ids": classified[r["id"]][1], "reason": "Offline test fixture"} for r in rows]


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_ranking_and_evidence(self):
        with patch("main.analyze_batch", side_effect=fake_ai) as ai:
            response = self.client.post("/analyze", data={"config": json.dumps(SETTINGS)}, files={"file": ("sample.csv", RAW, "text/csv")})
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["summary"]["uploaded_rows"], 11)
        self.assertEqual(result["summary"]["duplicate"], 1)
        self.assertEqual(result["summary"]["matched_unique_users"], 6)
        self.assertEqual(result["summary"]["needs_review"], 1)
        payment, ui = result["issues"]
        self.assertEqual(payment["score"], 80)
        self.assertEqual(ui["score"], 46.67)
        self.assertEqual(payment["unique_users"], 3)
        self.assertEqual(payment["messages"], 4)
        self.assertEqual(payment["repeat_mentions_not_counted"], 1)
        self.assertEqual(payment["evidence"][0]["name"], "Asha")
        self.assertEqual(len(ai.call_args.args[0]), 10)
        self.assertEqual({r["id"] for r in result["audit"]}, set(range(1, 12)))

    def test_company_priority_changes_ranking(self):
        rows, removed, total = read_feedback(RAW)
        rules = [dict(r) for r in SETTINGS["rules"]]
        rules[0]["priority"], rules[1]["priority"] = "low", "high"
        result = build_result(rows, fake_ai(rows), rules, removed, total, "Acme", "Shop")
        self.assertEqual(result["issues"][0]["id"], "ui")

    def test_same_name_different_users_and_same_user_different_problems(self):
        raw = b'user_id,name,feedback\nu1,Sam,same text\nu2,Sam,same text\nu1,Sam,different problem\n'
        rows, removed, total = read_feedback(raw)
        self.assertEqual(len(rows), 3)
        self.assertEqual(removed, [])

    def test_malformed_and_missing_columns(self):
        for raw in (b'feedback\nhello\n', b'user_id,name,feedback\nu1,Name,hello,unquoted\n', b'user_id,name,feedback\n,Name,hello\n'):
            with self.subTest(raw=raw), patch('main.analyze_batch') as ai:
                response=self.client.post('/analyze',data={'config':json.dumps(SETTINGS)},files={'file':('bad.csv',raw,'text/csv')})
                self.assertEqual(response.status_code,400)
                ai.assert_not_called()

    def test_csv_bom_quoted_commas_and_multiline(self):
        rows, _, _ = read_feedback('\ufeffuser_id,name,feedback\nu1,Sam,"hello,\nworld"\n'.encode())
        self.assertEqual(rows[0]['feedback'], 'hello,\nworld')

    def test_ai_duplicate_ids_and_invalid_topics_rejected(self):
        rows, removed, total = read_feedback(RAW)
        for corrupt in ('duplicate','topic'):
            items=fake_ai(rows)
            if corrupt=='duplicate': items[-1]=items[0]
            else: items[0]['rule_ids']=['invented']
            with self.assertRaises(ValueError):
                build_result(rows,items,SETTINGS['rules'],removed,total,'Acme','Shop')

    def test_all_irrelevant_returns_empty_table(self):
        rows, removed, total = read_feedback(RAW)
        items=[{'id':r['id'],'status':'irrelevant','rule_ids':[],'reason':'fixture'} for r in rows]
        result=build_result(rows,items,SETTINGS['rules'],removed,total,'Acme','Shop')
        self.assertEqual(result['issues'],[])
        self.assertEqual(result['summary']['matched_unique_users'],0)

    def test_routes_and_config_validation(self):
        for route in ('/', '/health', '/static/app.js', '/static/style.css', '/static/sample-feedback.csv'):
            self.assertEqual(self.client.get(route).status_code,200)
        response=self.client.post('/analyze',data={'config':'{}'},files={'file':('sample.csv',RAW,'text/csv')})
        self.assertEqual(response.status_code,400)


if __name__ == '__main__':
    unittest.main()
