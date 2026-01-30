"""
Routers module for data product publishing API.
"""
from . import drafts, submissions, validation, audit, evidence, auth

__all__ = ['auth', 'drafts', 'submissions', 'validation', 'audit', 'evidence']
