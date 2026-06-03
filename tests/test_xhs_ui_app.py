from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import xhs_ui_app


class XhsUiAppTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.old_jobs_dir = xhs_ui_app.JOBS_DIR
        self.old_data_dir = xhs_ui_app.DATA_DIR
        self.old_settings_path = xhs_ui_app.SETTINGS_PATH
        xhs_ui_app.DATA_DIR = Path(self.tmpdir.name) / "data"
        xhs_ui_app.JOBS_DIR = xhs_ui_app.DATA_DIR / "jobs"
        xhs_ui_app.SETTINGS_PATH = xhs_ui_app.DATA_DIR / "settings.json"
        xhs_ui_app.app.config.update(TESTING=True)
        self.client = xhs_ui_app.app.test_client()

    def tearDown(self) -> None:
        xhs_ui_app.DATA_DIR = self.old_data_dir
        xhs_ui_app.JOBS_DIR = self.old_jobs_dir
        xhs_ui_app.SETTINGS_PATH = self.old_settings_path

    def save_finished_job(self) -> str:
        job_id = "a" * 32
        job_dir = xhs_ui_app.JOBS_DIR / job_id
        rows = [
            {
                "index": 1,
                "risk_level": "high",
                "score": 4,
                "categories": "人身攻击/辱骂",
                "action": "优先处理",
                "reasons": "命中风险规则",
                "author": "",
                "time": "",
                "url": "https://www.xiaohongshu.com/example/1",
                "comment": "你就是个傻逼吧",
            },
            {
                "index": 2,
                "risk_level": "clean",
                "score": 0,
                "categories": "未命中",
                "action": "无需处理",
                "reasons": "未命中风险规则",
                "author": "",
                "time": "",
                "url": "https://www.xiaohongshu.com/example/1",
                "comment": "谢谢分享",
            },
        ]
        job = {
            "id": job_id,
            "url": "https://www.xiaohongshu.com/example/1",
            "status": "done",
            "message": "检测完成",
            "created_at": "2026-06-03T10:00:00",
            "updated_at": "2026-06-03T10:01:00",
            "comment_count": 2,
            "risky_count": 1,
            "clean_count": 1,
            "feedback_count": 0,
            "report_path": str(job_dir / "report.csv"),
        }
        xhs_ui_app.save_json(job_dir / "job.json", job)
        xhs_ui_app.save_json(job_dir / "rows.json", rows)
        return job_id

    def test_home_route_loads(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("粘贴帖子链接".encode(), response.data)

    def test_invalid_url_submission_is_rejected(self) -> None:
        response = self.client.post("/jobs", data={"url": "https://example.com"}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("请输入有效的小红书帖子链接".encode(), response.data)

    def test_result_rendering_works_from_saved_job(self) -> None:
        job_id = self.save_finished_job()
        response = self.client.get(f"/jobs/{job_id}/result")
        self.assertEqual(response.status_code, 200)
        self.assertIn("1 条评论需要关注".encode(), response.data)
        self.assertIn("你就是个傻逼吧".encode(), response.data)

    def test_job_counts_match_rows(self) -> None:
        rows = [
            {"risk_level": "critical"},
            {"risk_level": "high"},
            {"risk_level": "feedback"},
            {"risk_level": "clean"},
        ]
        self.assertEqual(
            xhs_ui_app.count_rows(rows),
            {
                "comment_count": 4,
                "risky_count": 2,
                "clean_count": 1,
                "feedback_count": 1,
            },
        )

    def test_model_settings_default_to_local_rules(self) -> None:
        settings = xhs_ui_app.load_model_settings()
        self.assertTrue(settings["enabled"])
        self.assertEqual(settings["model"], "deepseek-v4-flash")
        self.assertEqual(settings["base_url"], "https://api.deepseek.com")
        self.assertEqual(settings["llm_mode"], "all")
        self.assertEqual(settings["max_llm_comments"], 0)
        self.assertEqual(settings["collection_intensity"], "standard")
        self.assertEqual(settings["api_key"], "")

    def test_model_settings_save_masks_api_key_on_page(self) -> None:
        response = self.client.post(
            "/settings/model",
            data={
                "enabled": "on",
                "api_key": "sk-test-secret",
                "model": "deepseek-v4-flash",
                "base_url": "https://api.deepseek.com",
                "llm_mode": "all",
                "max_llm_comments": "12",
                "collection_intensity": "deep",
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("sk-****cret".encode(), response.data)
        self.assertNotIn("sk-test-secret".encode(), response.data)
        settings = xhs_ui_app.load_model_settings()
        self.assertTrue(settings["enabled"])
        self.assertEqual(settings["api_key"], "sk-test-secret")
        self.assertEqual(settings["llm_mode"], "all")
        self.assertEqual(settings["max_llm_comments"], 12)
        self.assertEqual(settings["collection_intensity"], "deep")

    def test_invalid_model_review_mode_is_rejected(self) -> None:
        response = self.client.post(
            "/settings/model",
            data={
                "enabled": "on",
                "api_key": "sk-test-secret",
                "model": "deepseek-v4-flash",
                "base_url": "https://api.deepseek.com",
                "llm_mode": "bad-mode",
                "max_llm_comments": "12",
                "collection_intensity": "standard",
            },
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("复核范围无效".encode(), response.data)
        self.assertFalse(xhs_ui_app.SETTINGS_PATH.exists())

    def test_classify_comments_uses_enabled_model_settings(self) -> None:
        class FakeModerator:
            def review(self, comment, rule_decision):
                return {
                    "risk_level": "medium",
                    "confidence": 0.9,
                    "categories": ["模型判断"],
                    "action": "人工复核",
                    "reason": "测试模型复核",
                }

        settings = {
            "enabled": True,
            "api_key": "sk-test-secret",
            "model": "deepseek-v4-flash",
            "base_url": "https://api.deepseek.com",
            "llm_mode": "all",
            "max_llm_comments": 1,
        }
        rows, warning = xhs_ui_app.classify_comments(
            ["这句话表面正常"],
            "https://www.xiaohongshu.com/example/1",
            settings=settings,
            llm_factory=lambda _: FakeModerator(),
        )
        self.assertIsNone(warning)
        self.assertEqual(rows[0]["llm_risk_level"], "medium")
        self.assertIn("模型判断", rows[0]["categories"])

    def test_classify_comments_requires_model_when_forced(self) -> None:
        settings = {
            "enabled": True,
            "api_key": "",
            "model": "deepseek-v4-flash",
            "base_url": "https://api.deepseek.com",
            "llm_mode": "all",
            "max_llm_comments": 0,
            "collection_intensity": "standard",
        }
        with self.assertRaisesRegex(RuntimeError, "强制模型复核"):
            xhs_ui_app.classify_comments(
                ["谢谢分享"],
                "https://www.xiaohongshu.com/example/1",
                settings=settings,
                llm_factory=lambda _: None,
            )

    def test_classify_comments_errors_when_forced_model_fails(self) -> None:
        class FailingModerator:
            def review(self, comment, rule_decision):
                raise RuntimeError("模型不可用")

        settings = {
            "enabled": True,
            "api_key": "sk-test-secret",
            "model": "deepseek-v4-flash",
            "base_url": "https://api.deepseek.com",
            "llm_mode": "all",
            "max_llm_comments": 0,
            "collection_intensity": "standard",
        }
        with self.assertRaisesRegex(RuntimeError, "模型复核失败"):
            xhs_ui_app.classify_comments(
                ["谢谢分享"],
                "https://www.xiaohongshu.com/example/1",
                settings=settings,
                llm_factory=lambda _: FailingModerator(),
            )

    def test_start_job_requires_api_key_in_forced_mode(self) -> None:
        response = self.client.post(
            "/jobs",
            data={"url": "https://www.xiaohongshu.com/example/1"},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("请先配置模型 API Key".encode(), response.data)

    def test_local_rule_mode_can_still_classify_without_model(self) -> None:
        settings = {
            "enabled": False,
            "api_key": "",
            "model": "deepseek-v4-flash",
            "base_url": "https://api.deepseek.com",
            "llm_mode": "all",
            "max_llm_comments": 0,
            "collection_intensity": "standard",
        }
        rows, warning = xhs_ui_app.classify_comments(
            ["谢谢分享"],
            "https://www.xiaohongshu.com/example/1",
            settings=settings,
            llm_factory=lambda _: None,
        )
        self.assertIsNone(warning)
        self.assertEqual(rows[0]["risk_level"], "clean")


if __name__ == "__main__":
    unittest.main()
