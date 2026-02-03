"""
PUBLIC_INTERFACE
Backward compatibility wrapper for submission service.

This module provides backward compatibility for existing code that imports SubmissionService.
New code should use DataAssetService from services.data_asset instead.

Deprecated: Use services.data_asset.DataAssetService
"""
import warnings
from services.data_asset import DataAssetService

warnings.warn(
    "services.submission.SubmissionService is deprecated. Use services.data_asset.DataAssetService instead.",
    DeprecationWarning,
    stacklevel=2
)

# Export DataAssetService as SubmissionService for backward compatibility
SubmissionService = DataAssetService

__all__ = ["SubmissionService"]
