from enum import Enum


class StrEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class UserRole(StrEnum):
    USER = "user"
    OPERATOR = "operator"
    ADMIN = "admin"


class DialogStatus(StrEnum):
    ACTIVE = "active"
    CLOSED = "closed"


class DialogMode(StrEnum):
    AI_SUPPORT = "ai_support"
    OPERATOR_SUPPORT = "operator_support"


class DialogChannel(StrEnum):
    WEB = "web"
    BITRIX24 = "bitrix24"
    REDMINE = "redmine"


class MessageAuthor(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    OPERATOR = "operator"
    SYSTEM = "system"


class MessageProcessingStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class FeedbackVerdict(StrEnum):
    HELPFUL = "helpful"
    AI_ERROR = "ai_error"


class CandidateStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class CandidateSource(StrEnum):
    USER_FEEDBACK = "user_feedback"
    OPERATOR = "operator"
    ADMIN = "admin"


class DocumentSourceType(StrEnum):
    OFFICIAL_1C_DOCS = "official_1c_docs"
    INTERNAL_KB = "internal_kb"
    RESOLVED_CASE = "resolved_case"


class IndexStatus(StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    INDEXED = "indexed"
    FAILED = "failed"


class PromptType(StrEnum):
    USER_SUPPORT = "user_support"
    OPERATOR_GIGACHAT = "operator_gigachat"
    KNOWLEDGE_CARD = "knowledge_card"


class MonitoringPeriod(StrEnum):
    TODAY = "today"
    DAYS_7 = "7d"
    DAYS_30 = "30d"
    ALL = "all"
