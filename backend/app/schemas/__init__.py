"""Imports of API schemes.

Author: Maxi-online
"""

from app.schemas.article import ArticleCreate, ArticleRead
from app.schemas.company import CompanyCreate, CompanyRead
from app.schemas.match_link import MatchLinkCreate, MatchLinkRead
from app.schemas.project import ProjectCreate, ProjectRead
from app.schemas.tender import TenderCreate, TenderRead
from app.schemas.source import SourceCreate, SourceRead
from app.schemas.nlp import TextRequestCreate
from app.schemas.keyword import (
    SearchKeywordCreate,
    SearchKeywordRead,
    SearchKeywordSetCreate,
    SearchKeywordSetRead,
    SearchKeywordSetUpdate,
)

__all__ = [
    "ArticleCreate",
    "ArticleRead",
    "CompanyCreate",
    "CompanyRead",
    "MatchLinkCreate",
    "MatchLinkRead",
    "ProjectCreate",
    "ProjectRead",
    "TenderCreate",
    "TenderRead",
    "SourceCreate",
    "SourceRead",
    "TextRequestCreate",
    "SearchKeywordCreate",
    "SearchKeywordRead",
    "SearchKeywordSetCreate",
    "SearchKeywordSetRead",
    "SearchKeywordSetUpdate",
]
