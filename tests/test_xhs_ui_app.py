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
        xhs_ui_app.DATA_DIR = Path(self.tmpdir.name) / "data"
        xhs_ui_app.JOBS_DIR = xhs_ui_app.DATA_DIR / "jobs"
        xhs_ui_app.app.config.update(TESTING=True)
        self.client = xhs_ui_app.app.test_client()

    def tearDown(self) -> None:
        xhs_ui_app.DATA_DIR = self.old_data_dir
        xhs_ui_app.JOBS_DIR = self.old_jobs_dir

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


if __name__ == "__main__":
    unittest.main()
