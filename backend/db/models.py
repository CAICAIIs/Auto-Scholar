import enum
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, Float, Index, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ProcessingStatus(enum.StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    authors: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    abstract: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    pdf_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    pdf_object_key: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)
    pdf_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    pdf_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pdf_downloaded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    core_contribution: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[ProcessingStatus] = mapped_column(
        Enum(ProcessingStatus), nullable=False, default=ProcessingStatus.PENDING, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_papers_status_created", "status", "created_at"),
        Index("ix_papers_pdf_hash", "pdf_content_hash"),
    )


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    paper_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    start_char: Mapped[int] = mapped_column(Integer, nullable=False)
    end_char: Mapped[int] = mapped_column(Integer, nullable=False)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[ProcessingStatus] = mapped_column(
        Enum(ProcessingStatus), nullable=False, default=ProcessingStatus.PENDING
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_chunks_paper_index", "paper_id", "chunk_index"),
        Index("ix_chunks_status", "status"),
        Index("ix_chunks_pages", "page_start", "page_end"),
    )


class Embedding(Base):
    __tablename__ = "embeddings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chunk_id: Mapped[int] = mapped_column(Integer, nullable=False)
    paper_id: Mapped[str] = mapped_column(String(255), nullable=False)
    vector_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    similarity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    extra_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[ProcessingStatus] = mapped_column(
        Enum(ProcessingStatus), nullable=False, default=ProcessingStatus.PENDING
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index("ix_embeddings_chunk", "chunk_id"),
        Index("ix_embeddings_paper", "paper_id"),
        Index("ix_embeddings_vector", "vector_id"),
        Index("ix_embeddings_status", "status"),
    )
