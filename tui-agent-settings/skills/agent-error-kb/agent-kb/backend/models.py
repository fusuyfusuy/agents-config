from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class Solution(BaseModel):
    id: Optional[str] = Field(None, description="Unique identifier for the solution")
    cause: str = Field(..., description="Root cause explanation of the error")
    patch_or_fix: str = Field(..., description="Concrete code diff, command, or patch to resolve the error")
    explanation: Optional[str] = Field("", description="Detailed context or rationale for the fix")
    tags: List[str] = Field(default_factory=list, description="Categorization tags (e.g. sqlite, async, permissions)")
    verification_score: float = Field(1.0, description="Community/agent confidence score (0.0 - 5.0)")
    verified_count: int = Field(1, description="Number of times this fix was successfully applied")
    created_at: Optional[str] = Field(None, description="ISO timestamp when recorded")

class ErrorRecord(BaseModel):
    id: Optional[str] = Field(None, description="Unique identifier for the error record")
    fingerprint: str = Field(..., description="SHA-256 hash fingerprint of normalized stack trace/message")
    error_type: str = Field(..., description="Class or category of error (e.g. OperationalError, JSONDecodeError)")
    error_message: str = Field(..., description="Raw error message")
    raw_stack_trace: str = Field(..., description="Original full stack trace")
    normalized_stack_trace: str = Field(..., description="Cleaned, normalized stack trace")
    agent_environment: Dict[str, Any] = Field(default_factory=dict, description="Agent environment metadata (OS, runtime, versions)")
    tags: List[str] = Field(default_factory=list, description="Associated issue tags")
    solutions: List[Solution] = Field(default_factory=list, description="Solutions linked to this error")
    created_at: Optional[str] = Field(None, description="ISO timestamp created")
    updated_at: Optional[str] = Field(None, description="ISO timestamp updated")

class RecordInput(BaseModel):
    error_type: str = Field(..., description="Type of error (e.g. PermissionError)")
    error_message: str = Field(..., description="Error message text")
    stack_trace: str = Field("", description="Stack trace content")
    cause: str = Field(..., description="Root cause description")
    patch_or_fix: str = Field(..., description="Fix code/command/patch")
    explanation: Optional[str] = Field("", description="Explanation of why fix works")
    tags: List[str] = Field(default_factory=list, description="Issue tags")
    agent_environment: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Agent environment metadata")
    verification_score: float = Field(1.0, description="Verification score rating")

class SearchQuery(BaseModel):
    query: str = Field(..., description="Error log, stack trace, or description query")
    error_type: Optional[str] = Field(None, description="Filter by error type")
    tags: Optional[List[str]] = Field(None, description="Filter by tag list")
    limit: int = Field(5, description="Maximum number of results to return")
    min_score: float = Field(0.0, description="Minimum confidence score threshold")

class SearchResult(BaseModel):
    record: ErrorRecord = Field(..., description="Matching error record")
    matched_solution: Solution = Field(..., description="Best solution for the matched record")
    confidence_score: float = Field(..., description="Match confidence score (0.0 to 1.0)")
    match_type: str = Field(..., description="Type of match: fingerprint_exact, fts5_keyword, or token_similarity")
    explanation: str = Field(..., description="Human-readable explanation of why this solution was matched")

class ErrorPattern(BaseModel):
    tag: str = Field(..., description="Tag name representing an error category/pattern")
    count: int = Field(..., description="Number of error records with this tag")
    avg_verification_score: float = Field(..., description="Average verification score of associated solutions")
    sample_error_types: List[str] = Field(default_factory=list, description="Sample error types for this pattern")
