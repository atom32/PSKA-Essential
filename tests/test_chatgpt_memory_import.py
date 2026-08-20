from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pska_essential.chatgpt_memory_import import build_chatgpt_memory_summary_import
from pska_essential.workflow import build_fake_service


CHATGPT_MEMORY_SAMPLE = """
个性化-记忆（旧版）：
用户长期项目 PSKA 的核心目标之一是构建一个与其个人记忆、知识存量和思维习惯高度贴合的外挂智能。

用户有一段较长的人生回忆，核心内容包括与高晓茜、窦宁等人的私密人生经历。

记忆（新版）：
教育与职业背景
你叫徐大为，成长于锦州，目前生活在天津。你本科毕业于天津大学软件工程专业，之后在天津大学与日本 JAIST 完成双硕士，并于 JAIST 获得信息科学博士学位。

长期项目
你持续投入多个长期项目。其中最核心的是 PSKA，希望把它打造为个人的外挂智能，结合自己的知识、记忆和思考方式，实现长期知识保存、检索与证据驱动推理。

兴趣爱好
你长期关注高达、EVA、战锤40K、型月等作品，也喜欢推理、剧本杀、都市怪谈等创作话题。
"""


class ChatGPTMemorySummaryImportTests(unittest.TestCase):
    def test_import_creates_governed_candidates_and_skips_private_by_default(self):
        service = build_fake_service()

        result = build_chatgpt_memory_summary_import(
            service,
            text=CHATGPT_MEMORY_SAMPLE,
            source_label="ChatGPT memory export",
            candidate_limit=8,
        )

        self.assertEqual(result["schema"], "pska.chatgpt_memory_summary_import.v1")
        self.assertEqual(result["status"], "created")
        self.assertGreaterEqual(result["summary"]["created_count"], 3)
        self.assertEqual(result["summary"]["skipped_private_count"], 1)
        self.assertTrue(result["summary"]["privacy_boundary_created"])
        self.assertFalse(result["data_flow"]["writes_memory_directly"])
        self.assertFalse(result["data_flow"]["writes_source_files"])
        self.assertTrue(result["data_flow"]["creates_review"])
        created_text = json.dumps(result["candidate_result"]["created"], ensure_ascii=False)
        self.assertIn("PSKA", created_text)
        self.assertIn("隐私", created_text)
        self.assertNotIn("高晓茜", created_text)
        self.assertNotIn("窦宁", created_text)
        result_text = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("高晓茜", result_text)
        self.assertNotIn("窦宁", result_text)
        self.assertEqual(result["skipped_private"][0]["preview"], "[private source archive entry redacted]")

        reviews = service.store.list_reviews(status="pending", limit=20)
        self.assertEqual(len(reviews), result["summary"]["created_count"])
        self.assertEqual(service.memory.search("外挂智能", {}, 10), [])
        audit_events = service.store.list_audit_events(action="chatgpt.memory_summary.import", limit=1)
        self.assertEqual(len(audit_events), 1)
        audit_text = json.dumps(audit_events[0].metadata, ensure_ascii=False)
        self.assertNotIn("高晓茜", audit_text)
        self.assertNotIn("窦宁", audit_text)

    def test_import_can_read_from_source_path_without_writing_source_files(self):
        service = build_fake_service()
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "chatgpt-memory.md"
            path.write_text(CHATGPT_MEMORY_SAMPLE, encoding="utf-8")

            result = build_chatgpt_memory_summary_import(
                service,
                source_path=str(path),
                candidate_limit=4,
            )

        self.assertEqual(result["source"]["label"], "chatgpt-memory.md")
        self.assertTrue(result["data_flow"]["reads_source_path"])
        self.assertFalse(result["data_flow"]["writes_source_files"])


if __name__ == "__main__":
    unittest.main()
