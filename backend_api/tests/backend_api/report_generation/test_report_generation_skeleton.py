import pytest


@pytest.mark.api
def test_report_generation_trigger_and_retrieve__todo():
    """
    Feature: report_generation

    TODO:
    - Implement once report generation/validation run APIs are finalized.
    - Suggested flow:
        1) Create draft/submission
        2) Trigger validation/report generation
        3) Retrieve report by validation_run_id
        4) Assert stable schema + overall_status + hash fields
    """
    pytest.skip("TODO(report_generation): Implement trigger + retrieve report tests when feature is finalized.")
