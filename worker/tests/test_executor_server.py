from pathlib import Path
from io import BytesIO
import base64

from fastapi.testclient import TestClient
from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]

from maga_worker import executor_server  # noqa: E402
from maga_worker.executor_server import app  # noqa: E402


def _client(monkeypatch):
    monkeypatch.setenv("MAGA_WORKER_EXECUTOR_TOKEN", "test-token")
    monkeypatch.delenv("XHS_WRITER_EXECUTOR_TOKEN", raising=False)
    return TestClient(app)


def _headers(token="test-token"):
    return {
        "X-Maga-Protocol-Version": "0.1",
        "Authorization": f"Bearer {token}",
    }


def _envelope(capability, input_payload=None, stage_call_id="stage-001"):
    return {
        "protocol_version": "0.1",
        "run_id": 10,
        "task_id": 20,
        "stage_call_id": stage_call_id,
        "capability": capability,
        "executor_hints": {"timeout_seconds": 60},
        "input": input_payload or {},
    }


def test_invoke_rejects_missing_protocol_header(monkeypatch):
    client = _client(monkeypatch)

    response = client.post("/invoke", json=_envelope("xhs.interpret_brief"), headers={"Authorization": "Bearer test-token"})

    assert response.status_code == 400
    assert response.json()["detail"] == "unsupported protocol version"


def test_invoke_rejects_wrong_bearer_token(monkeypatch):
    client = _client(monkeypatch)

    response = client.post("/invoke", json=_envelope("xhs.interpret_brief"), headers=_headers("wrong-token"))

    assert response.status_code == 401


def test_interpret_brief_returns_protocol_succeeded_envelope(monkeypatch):
    client = _client(monkeypatch)

    response = client.post(
        "/invoke",
        json=_envelope(
            "xhs.interpret_brief",
            {
                "product_topic": "美素佳儿源悦",
                "target_audience": "新手妈妈",
                "style": "情绪共情",
                "generation_snapshot": {
                    "brief": {
                        "product_topic": "宝宝便便不规律",
                        "target_audience": "新手妈妈",
                        "style": "经验老道型",
                    },
                    "assets": {"painpoint": {"painpoint": "便便不规律"}},
                    "batch_context": {"batch_code": "unit", "item_no": 2},
                },
            },
        ),
        headers=_headers(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["stage_call_id"] == "stage-001"
    assert data["status"] == "succeeded"
    assert data["output"]["structured_brief"]["product_topic"] == "美素佳儿源悦"
    assert data["output"]["structured_brief"]["target_audience"] == "新手妈妈"
    assert data["output"]["runtime_brief"]["brief_id"] == "maga-unit-002"
    assert data["output"]["runtime_brief"]["key_painpoints"] == ["便便不规律"]
    assert data["output"]["brief_warnings"] == []
    assert data["stats"]["executor"] == "maga-worker"
    assert data["stats"]["module"] == "xhs-writer"


def test_generate_draft_stub_returns_draft_for_maga_smoke(monkeypatch):
    client = _client(monkeypatch)

    response = client.post(
        "/invoke",
        json=_envelope(
            "xhs.generate_draft",
            {
                "structured_brief": {
                    "product_topic": "美素佳儿源悦",
                    "target_audience": "新手妈妈",
                    "style": "情绪共情",
                },
                "analyses": {},
            },
            stage_call_id="stage-draft",
        ),
        headers=_headers(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["stage_call_id"] == "stage-draft"
    assert data["status"] == "succeeded"
    assert data["output"]["draft"]["title"]
    assert "新手妈妈" in data["output"]["draft"]["body"]


def test_asset_import_returns_structured_asset_package(monkeypatch):
    client = _client(monkeypatch)
    wb = Workbook()
    ws = wb.active
    ws.title = "品牌资料整理"
    ws["C3"] = "好消化易吸收，对应便便好，不上火"
    ws["C4"] = "高质量真实用户ugc"
    ws["B8"] = "分级"
    ws["C8"] = "卖点"
    ws["D8"] = "成分"
    ws["E8"] = "源悦优势"
    ws["F8"] = "生动理解"
    ws["B9"] = "核心卖点"
    ws["C9"] = "好消化易吸收"
    ws["D9"] = "软分子蛋白"
    ws["E9"] = "形成结构松散的软凝乳"
    ws["F9"] = "软软的米糊"

    ws2 = wb.create_sheet("内容模型")
    ws2.append(["序号", "宝宝阶段", "核心痛点", "具体表现", "痛点描述", "对应卖点"])
    ws2.append([None, None, "便便不规律", "羊屎蛋/干硬", "便便又干又硬", "好消化易吸收"])
    ws2.append([None, None, None, "拉臭费劲", "拉起来不轻松", "好消化易吸收"])

    ws3 = wb.create_sheet("ugc常规-卖点表述")
    ws3.append(["序号", "对应卖点", "卖点描述", "负责人"])
    ws3.append([None, "便便不规律", "便便基本一天一次，拉起来也不费劲", "东昕"])

    ws4 = wb.create_sheet("审核规则")
    ws4.append(["序号", "审核内容", "分类", "审核维度（问题分类）", "审核意见（返回给用户的）"])
    ws4.append([1, "文案审核", "草稿审核", "夸大产品效果或虚构使用经历", "文本不符合活动要求"])

    bio = BytesIO()
    wb.save(bio)
    content = bio.getvalue()

    response = client.post(
        "/invoke",
        json=_envelope(
            "asset.import",
            {
                "asset_key": "yuanyue",
                "source_name": "源悦种草活动-ai训练规则.xlsx",
                "source_hash": "hash-001",
                "source_content_base64": base64.b64encode(content).decode("ascii"),
            },
            stage_call_id="stage-asset-import",
        ),
        headers=_headers(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "succeeded"
    assert data["stats"]["module"] == "asset-steward"
    output = data["output"]
    assert output["asset_key"] == "yuanyue"
    by_type = {asset["asset_type"]: asset for asset in output["assets"]}
    assert by_type["brand_profile"]["content_json"]["content_style"] == "高质量真实用户ugc"
    assert by_type["product_selling_points"]["content_json"]["items"][0]["selling_point"] == "好消化易吸收"
    topic = by_type["painpoint_model"]["content_json"]["topics"][0]
    assert topic["topic"] == "便便不规律"
    assert topic["descriptions"] == ["羊屎蛋/干硬", "便便又干又硬", "拉臭费劲", "拉起来不轻松"]
    assert topic["selling_points"][0]["selling_point"] == "好消化易吸收"
    assert by_type["ugc_expression_corpus"]["content_json"]["items"][0]["expression"] == "便便基本一天一次，拉起来也不费劲"


def test_generate_draft_runtime_mode_uses_runtime_adapter(monkeypatch):
    calls = {}

    def fake_invoke_runtime_generate_draft(generation_snapshot, runtime_brief=None):
        calls["snapshot"] = generation_snapshot
        calls["runtime_brief"] = runtime_brief
        return {
            "draft": {"title": "源悦真实 runtime 标题", "body": "runtime 正文"},
            "runtime_result": {"verdict": "pass", "soft_score": 90},
        }

    monkeypatch.setenv("XHS_WRITER_EXECUTION_MODE", "runtime")
    monkeypatch.setattr(executor_server, "invoke_runtime_generate_draft", fake_invoke_runtime_generate_draft)
    client = _client(monkeypatch)
    snapshot = {
        "brief": {"product_topic": "宝宝便便不规律", "target_audience": "新手妈妈", "style": "经验老道型"},
        "assets": {"painpoint": {"painpoint": "便便不规律"}},
        "diversity_slot": {"opening_type": "过来人提醒"},
    }

    response = client.post(
        "/invoke",
        json=_envelope(
            "xhs.generate_draft",
            {
                "structured_brief": {"product_topic": "宝宝便便不规律"},
                "generation_snapshot": snapshot,
                "runtime_brief": {"brief_id": "compiled-runtime", "product_topic": "宝宝便便不规律"},
            },
            stage_call_id="stage-runtime",
        ),
        headers=_headers(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["output"]["draft"]["title"] == "源悦真实 runtime 标题"
    assert data["output"]["runtime_result"]["soft_score"] == 90
    assert calls["snapshot"] == snapshot
    assert calls["runtime_brief"]["brief_id"] == "compiled-runtime"


def test_generate_draft_runtime_fast_mode_uses_fast_runtime_adapter(monkeypatch):
    calls = {}

    def fake_invoke_runtime_fast_generate_draft(generation_snapshot, runtime_brief=None):
        calls["snapshot"] = generation_snapshot
        calls["runtime_brief"] = runtime_brief
        return {
            "draft": {"title": "源悦 runtime fast 标题", "body": "runtime fast 正文"},
            "runtime_result": {"mode": "runtime_fast", "final_path": "/tmp/final.md"},
        }

    monkeypatch.setenv("XHS_WRITER_EXECUTION_MODE", "runtime_fast")
    monkeypatch.setattr(executor_server, "invoke_runtime_fast_generate_draft", fake_invoke_runtime_fast_generate_draft)
    client = _client(monkeypatch)
    snapshot = {
        "brief": {"product_topic": "宝宝便便不规律", "target_audience": "新手妈妈", "style": "经验老道型"},
        "assets": {"painpoint": {"painpoint": "便便不规律"}},
    }

    response = client.post(
        "/invoke",
        json=_envelope(
            "xhs.generate_draft",
            {"generation_snapshot": snapshot, "runtime_brief": {"brief_id": "compiled-fast"}},
            stage_call_id="stage-runtime-fast",
        ),
        headers=_headers(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["output"]["draft"]["title"] == "源悦 runtime fast 标题"
    assert data["output"]["runtime_result"]["mode"] == "runtime_fast"
    assert "review_report" not in data["output"]
    assert calls["snapshot"] == snapshot
    assert calls["runtime_brief"]["brief_id"] == "compiled-fast"


def test_review_and_rewrite_runtime_fast_uses_fast_runtime_adapter(monkeypatch):
    calls = {}

    def fake_invoke_runtime_fast_review_and_rewrite(generation_snapshot, draft, runtime_brief=None):
        calls["snapshot"] = generation_snapshot
        calls["draft"] = draft
        calls["runtime_brief"] = runtime_brief
        return {
            "final": {"title": "审核后标题", "body": "审核后正文"},
            "draft": {"title": "审核后标题", "body": "审核后正文"},
            "runtime_result": {"mode": "runtime_fast", "phase": "review_and_rewrite", "final_path": "/tmp/final.md"},
            "review_report": {
                "hard_results": [{"ae_code": "compliance_redline", "pass": True}],
                "soft_scores": [],
                "rewrite_required": False,
            },
        }

    monkeypatch.setattr(
        executor_server,
        "invoke_runtime_fast_review_and_rewrite",
        fake_invoke_runtime_fast_review_and_rewrite,
    )
    client = _client(monkeypatch)
    snapshot = {"brief": {"product_topic": "宝宝便便不规律"}, "assets": {}}
    draft = {"title": "初稿标题", "body": "初稿正文"}

    response = client.post(
        "/invoke",
        json=_envelope(
            "xhs.review_and_rewrite",
            {"generation_snapshot": snapshot, "draft": draft, "runtime_brief": {"brief_id": "compiled-review"}},
            stage_call_id="stage-review-rewrite",
        ),
        headers=_headers(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["output"]["final"]["title"] == "审核后标题"
    assert data["output"]["runtime_result"]["phase"] == "review_and_rewrite"
    assert data["output"]["hard_results"][0]["ae_code"] == "compliance_redline"
    assert calls == {"snapshot": snapshot, "draft": draft, "runtime_brief": {"brief_id": "compiled-review"}}


def test_generate_draft_maga_worker_execution_mode_env_overrides_legacy_env(monkeypatch):
    calls = {}

    def fake_invoke_runtime_fast_generate_draft(generation_snapshot, runtime_brief=None):
        calls["snapshot"] = generation_snapshot
        calls["runtime_brief"] = runtime_brief
        return {
            "draft": {"title": "MAGA worker runtime fast 标题", "body": "MAGA worker runtime fast 正文"},
            "runtime_result": {"mode": "runtime_fast", "final_path": "/tmp/maga-worker-runtime-fast/final.md"},
        }

    monkeypatch.setenv("MAGA_WORKER_EXECUTION_MODE", "runtime_fast")
    monkeypatch.setenv("XHS_WRITER_EXECUTION_MODE", "deterministic")
    monkeypatch.setattr(executor_server, "invoke_runtime_fast_generate_draft", fake_invoke_runtime_fast_generate_draft)
    client = _client(monkeypatch)
    snapshot = {
        "brief": {"product_topic": "宝宝便便不规律", "target_audience": "新手妈妈", "style": "经验老道型"},
        "assets": {"painpoint": {"painpoint": "便便不规律"}},
    }

    response = client.post(
        "/invoke",
        json=_envelope(
            "xhs.generate_draft",
            {"generation_snapshot": snapshot},
            stage_call_id="stage-maga-worker-runtime-fast",
        ),
        headers=_headers(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["output"]["draft"]["title"] == "MAGA worker runtime fast 标题"
    assert data["output"]["runtime_result"]["mode"] == "runtime_fast"
    assert calls["snapshot"] == snapshot
    assert calls["runtime_brief"] is None


def test_generate_draft_with_generation_snapshot_defaults_to_runtime_fast(monkeypatch):
    calls = {}

    def fake_invoke_runtime_fast_generate_draft(generation_snapshot, runtime_brief=None):
        calls["snapshot"] = generation_snapshot
        calls["runtime_brief"] = runtime_brief
        return {
            "draft": {"title": "自动 runtime fast 标题", "body": "自动 runtime fast 正文"},
            "runtime_result": {"mode": "runtime_fast", "final_path": "/tmp/auto-runtime-fast/final.md"},
        }

    monkeypatch.delenv("MAGA_WORKER_EXECUTION_MODE", raising=False)
    monkeypatch.delenv("XHS_WRITER_EXECUTION_MODE", raising=False)
    monkeypatch.setattr(executor_server, "invoke_runtime_fast_generate_draft", fake_invoke_runtime_fast_generate_draft)
    client = _client(monkeypatch)
    snapshot = {
        "brief": {"product_topic": "宝宝便便不规律", "target_audience": "新手妈妈", "style": "经验老道型"},
        "assets": {"painpoint": {"painpoint": "便便不规律"}},
    }

    response = client.post(
        "/invoke",
        json=_envelope(
            "xhs.generate_draft",
            {"generation_snapshot": snapshot},
            stage_call_id="stage-auto-runtime-fast",
        ),
        headers=_headers(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["output"]["draft"]["title"] == "自动 runtime fast 标题"
    assert data["output"]["runtime_result"]["mode"] == "runtime_fast"
    assert calls["snapshot"] == snapshot
    assert calls["runtime_brief"] is None


def test_generate_draft_runtime_fast_fake_mode_keeps_protocol_smoke_model_free(monkeypatch):
    monkeypatch.delenv("MAGA_WORKER_EXECUTION_MODE", raising=False)
    monkeypatch.delenv("XHS_WRITER_EXECUTION_MODE", raising=False)
    monkeypatch.setenv("MAGA_WORKER_RUNTIME_FAST_FAKE", "1")
    client = _client(monkeypatch)
    snapshot = {
        "brief": {"product_topic": "宝宝便便不规律", "target_audience": "新手妈妈", "style": "经验老道型"},
        "assets": {"painpoint": {"painpoint": "便便不规律"}},
    }

    response = client.post(
        "/invoke",
        json=_envelope(
            "xhs.generate_draft",
            {
                "structured_brief": {
                    "product_topic": "宝宝便便不规律",
                    "target_audience": "新手妈妈",
                    "style": "经验老道型",
                },
                "generation_snapshot": snapshot,
            },
            stage_call_id="stage-runtime-fast-fake",
        ),
        headers=_headers(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["output"]["runtime_result"] == {
        "mode": "runtime_fast",
        "fake": True,
        "reason": "MAGA_WORKER_RUNTIME_FAST_FAKE",
    }
    assert "review_report" not in data["output"]


def test_comment_generate_fake_mode_returns_stable_comment(monkeypatch):
    monkeypatch.setenv("MAGA_WORKER_RUNTIME_FAST_FAKE", "1")
    client = _client(monkeypatch)

    response = client.post(
        "/invoke",
        json=_envelope(
            "comment.generate",
            {
                "item_no": 1,
                "comment_angle": "整体适应",
                "corpus": "整体适应：\n像妈妈在评论区聊刚开始喝源悦的观察。",
                "examples": ["我家刚开始也在看源悦，想蹲蹲真实反馈"],
                "supplements": ["有同月龄宝宝喝过吗，想看看大家怎么说"],
            },
            stage_call_id="stage-comment-fake",
        ),
        headers=_headers(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["stage_call_id"] == "stage-comment-fake"
    assert data["status"] == "succeeded"
    assert data["stats"]["module"] == "comment-generator"
    assert data["output"]["comment"] == "我家刚开始也在看源悦，想蹲蹲真实反馈"
    assert data["output"]["runtime_result"] == {
        "mode": "comment_fake",
        "fake": True,
        "reason": "MAGA_WORKER_RUNTIME_FAST_FAKE",
    }


def test_content_generate_fake_mode_returns_comment_from_unified_input(monkeypatch):
    monkeypatch.setenv("MAGA_WORKER_RUNTIME_FAST_FAKE", "1")
    client = _client(monkeypatch)

    response = client.post(
        "/invoke",
        json=_envelope(
            "content.generate",
            {
                "content_type": "comment",
                "output_fields": ["comment"],
                "business_rule": {
                    "item_no": 1,
                    "comment_angle": "整体适应",
                    "corpus": "整体适应：\n像妈妈在评论区聊刚开始喝源悦的观察。",
                    "examples": ["我家刚开始也在看源悦，想蹲蹲真实反馈"],
                },
                "selected_keywords": [
                    {"category_code": "persona", "keyword_name": "经验型妈妈", "corpus": ["自然交流"]}
                ],
                "expert": {"expert_config_code": "comment_generator_v1"},
                "rendered_prompt": "生成一条评论",
            },
            stage_call_id="stage-content-fake",
        ),
        headers=_headers(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["stage_call_id"] == "stage-content-fake"
    assert data["status"] == "succeeded"
    assert data["stats"]["module"] == "content-generator"
    assert data["output"]["comment"] == "我家刚开始也在看源悦，想蹲蹲真实反馈"
    assert data["output"]["runtime_result"]["mode"] == "content_fake"
    assert data["output"]["runtime_result"]["expert_config_code"] == "comment_generator_v1"


def test_content_rewrite_fake_mode_removes_forbidden_terms(monkeypatch):
    monkeypatch.setenv("MAGA_WORKER_RUNTIME_FAST_FAKE", "1")
    client = _client(monkeypatch)

    response = client.post(
        "/invoke",
        json=_envelope(
            "content.rewrite",
            {
                "content_type": "comment",
                "output_fields": ["comment"],
                "previous_content": {"comment": "我家刚开始也在看源悦，想蹲蹲真实反馈"},
                "forbidden_hits": ["源悦"],
                "rewrite_instructions": ["删除或自然替换命中的违禁词"],
            },
            stage_call_id="stage-content-rewrite-fake",
        ),
        headers=_headers(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["stage_call_id"] == "stage-content-rewrite-fake"
    assert data["status"] == "succeeded"
    assert data["stats"]["module"] == "content-generator"
    assert data["output"]["comment"] == "我家刚开始也在看，想蹲蹲真实反馈"
    assert "源悦" not in data["output"]["comment"]
    assert data["output"]["runtime_result"]["mode"] == "content_rewrite_fake"


def test_content_rewrite_fake_mode_applies_forbidden_replacements(monkeypatch):
    monkeypatch.setenv("MAGA_WORKER_RUNTIME_FAST_FAKE", "1")
    client = _client(monkeypatch)

    response = client.post(
        "/invoke",
        json=_envelope(
            "content.rewrite",
            {
                "content_type": "comment",
                "output_fields": ["comment"],
                "previous_content": {"comment": "🍼接受度比之前稳定，想蹲蹲真实反馈"},
                "forbidden_hits": ["🍼"],
                "forbidden_replacements": {"🍼": "奶瓶"},
                "rewrite_instructions": ["指定替换映射：🍼 -> 奶瓶"],
            },
            stage_call_id="stage-content-rewrite-replacement",
        ),
        headers=_headers(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "succeeded"
    assert data["output"]["comment"] == "奶瓶接受度比之前稳定，想蹲蹲真实反馈"
    assert "🍼" not in data["output"]["comment"]


def test_content_rewrite_fake_mode_uses_operator_feedback(monkeypatch):
    monkeypatch.setenv("MAGA_WORKER_RUNTIME_FAST_FAKE", "1")
    client = _client(monkeypatch)

    response = client.post(
        "/invoke",
        json=_envelope(
            "content.rewrite",
            {
                "content_type": "article",
                "output_fields": ["title", "body"],
                "previous_content": {"title": "原标题", "body": "原正文比较总结。"},
                "operator_feedback": "开头再具体一点，少一点总结腔。",
                "rewrite_instructions": ["根据运营修改意见调整内容"],
            },
            stage_call_id="stage-content-rewrite-feedback",
        ),
        headers=_headers(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "succeeded"
    assert data["output"]["title"] == "原标题"
    assert "按运营反馈调整：开头再具体一点" in data["output"]["body"]
    assert data["output"]["runtime_result"]["mode"] == "content_rewrite_fake"


def test_run_ae_review_returns_structured_review_report(monkeypatch):
    client = _client(monkeypatch)

    response = client.post(
        "/invoke",
        json=_envelope(
            "xhs.run_ae_review",
            {
                "draft": {"title": "便便不规律别急", "body": "源悦好消化易吸收，日常观察不替代专业建议。"},
                "structured_brief": {"product_topic": "宝宝便便不规律"},
                "generation_snapshot": {
                    "assets": {"compliance_rules": [{"dimension": "禁止治疗便秘", "risk_level": "high"}]}
                },
            },
            stage_call_id="stage-review",
        ),
        headers=_headers(),
    )

    assert response.status_code == 200
    data = response.json()
    report = data["output"]["review_report"]
    assert report["rewrite_required"] is False
    assert report["risk_level"] == "high"
    assert data["output"]["hard_results"] == report["hard_results"]
    assert [item["ae_code"] for item in report["hard_results"]] == [
        "brand_product_guard",
        "compliance_redline",
        "expression_writing",
        "time_logic",
        "legal_tencent",
    ]
    assert {item["ae_code"] for item in report["soft_scores"]} == {"business_logic"}


def test_unknown_capability_returns_protocol_failed_envelope(monkeypatch):
    client = _client(monkeypatch)

    response = client.post("/invoke", json=_envelope("xhs.unknown", stage_call_id="stage-bad"), headers=_headers())

    assert response.status_code == 200
    data = response.json()
    assert data == {
        "stage_call_id": "stage-bad",
        "status": "failed",
        "error_code": "input_invalid",
        "error_message": "unsupported capability: xhs.unknown",
    }
