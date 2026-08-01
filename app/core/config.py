from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"), env_file_encoding="utf-8", extra="ignore"
    )

    APP_NAME: str = "DocumetsToAiPipeLine"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    # Document source — 실제 경로는 .env / .env.local 에서 지정
    DOCUMENTS_ROOT: str = "./data/documents"
    LEGACY_DOCS_ROOT: str = "./data/legacy-docs"

    # Database
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/rag_pipeline"

    # Vector DB
    VECTOR_DB_TYPE: str = "chroma"  # chroma | pgvector
    CHROMA_PERSIST_DIR: str = "./chroma_data"
    CHROMA_COLLECTION_NAME: str = "documents"

    # Embedding
    EMBEDDING_PROVIDER: str = "local"  # "openai" | "local"
    EMBEDDING_MODEL: str = "text-embedding-3-large"
    EMBEDDING_DIMENSION: int = 3072
    EMBEDDING_LOCAL_MODEL: str = "upskyy/bge-m3-korean"
    EMBEDDING_LOCAL_DEVICE: str = "cuda"  # "cuda" | "cpu"
    EMBEDDING_LOCAL_BATCH_SIZE: int = 64

    # LLM / External API keys
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    LLM_MODEL: str = "claude-sonnet-4-5-20250929"

    # Chunking
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200

    # Phase 2: 병렬 처리
    CONVERTER_CONCURRENCY: int = 10
    EMBEDDING_REQUESTS_PER_MINUTE: int = 3000
    EMBEDDING_TOKENS_PER_MINUTE: int = 900000
    EMBEDDING_BATCH_MAX_TOKENS: int = 8000
    STORE_BATCH_SIZE: int = 500

    # Phase 2: 진행률 추적
    PROGRESS_DB_PATH: str = "./progress.db"
    PROGRESS_LOG_INTERVAL: int = 30

    # Phase 2: 재시도
    MAX_RETRIES: int = 3
    RETRY_BASE_DELAY: float = 1.0
    RETRY_MAX_DELAY: float = 60.0


settings = Settings()
