"""
Routers for the Data Product Publishing API.
"""
from . import auth, drafts, data_assets, submissions, validation, audit, evidence, submissions_compat

__all__ = ["auth", "drafts", "data_assets", "submissions", "validation", "audit", "evidence", "submissions_compat"]
