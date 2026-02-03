import pytest


@pytest.mark.api
def test_dataset_upload_contract__todo():
    """
    Feature: dataset_upload

    TODO:
    - Implement when backend exposes a dataset upload endpoint (multipart or similar),
      or when "draft creation" is defined as dataset upload for this product.
    - Expected checks:
        - 201 Created on valid upload
        - deterministic error responses on invalid payload/file
        - persisted dataset metadata retrievable by id
    """
    pytest.skip("TODO(dataset_upload): No explicit dataset upload endpoint/tests implemented yet.")
