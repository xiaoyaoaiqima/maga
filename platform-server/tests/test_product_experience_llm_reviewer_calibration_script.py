from scripts.calibrate_product_experience_llm_reviewer import CALIBRATION_CASES


def test_product_experience_llm_reviewer_calibration_cases_cover_core_boundaries():
    by_id = {case.case_id: case for case in CALIBRATION_CASES}

    assert by_id["acceptable_light_seed"].expected_severities == {"pass", "minor"}
    assert by_id["acceptable_strong_seed_qa"].expected_severities == {"pass", "minor"}
    assert by_id["acceptable_node_rich_seed"].expected_severities == {"pass", "minor"}
    assert by_id["product_as_problem_answer_claim"].expected_severities == {"hard"}
    assert by_id["wrong_product_action_surface"].expected_severities == {"hard"}
    assert by_id["overcomplete_decision_chain"].expected_severities == {"rewrite", "hard"}
    assert by_id["template_reassurance_closure"].expected_severities == {"rewrite", "hard"}
    assert by_id["compliance_uncertainty_no_value"].expected_severities == {"rewrite", "hard"}
    assert by_id["brief_translation_tone"].expected_severities == {"rewrite", "hard"}
    assert by_id["medical_health_claim_context"].expected_severities == {"rewrite", "hard"}
