from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(500))
    role: Mapped[str] = mapped_column(String(20), default="VIEWER")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Analyst(Base):
    __tablename__ = "analysts"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    email: Mapped[str | None] = mapped_column(String(180))
    role_title: Mapped[str | None] = mapped_column(String(100), default="Analista")
    # Fotos podem chegar perto de 2 MB. Mantemos a coluna deferida para que
    # listagens e páginas comuns não trafeguem Base64 desnecessariamente.
    photo_data: Mapped[str | None] = mapped_column(Text, deferred=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    projects: Mapped[list["Project"]] = relationship(back_populates="analyst")


class Client(Base):
    __tablename__ = "clients"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(180), unique=True, index=True)
    segment: Mapped[str | None] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # O dashboard percorre a carteira para consolidar potencial financeiro.
    # selectin evita uma consulta individual por cliente (problema N+1).
    projects: Mapped[list["Project"]] = relationship(back_populates="client", lazy="selectin")


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"), index=True)
    analyst_id: Mapped[int | None] = mapped_column(ForeignKey("analysts.id"), index=True)
    product: Mapped[str] = mapped_column(String(20), default="Locator", index=True)
    portfolio_name: Mapped[str | None] = mapped_column(String(180))
    model: Mapped[str | None] = mapped_column(String(120))
    poc_start_date: Mapped[date | None] = mapped_column(Date)
    poc_end_date: Mapped[date | None] = mapped_column(Date)
    target_date: Mapped[date | None] = mapped_column(Date)
    go_live_date: Mapped[date | None] = mapped_column(Date)
    stage: Mapped[str] = mapped_column(String(80), default="Planejamento")
    status: Mapped[str] = mapped_column(String(80), default="Em andamento")
    health: Mapped[str] = mapped_column(String(20), default="Saudável")
    priority: Mapped[str] = mapped_column(String(20), default="Média")
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    potential_revenue: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=0)
    objective: Mapped[str | None] = mapped_column(Text)
    next_step: Mapped[str | None] = mapped_column(Text)
    blocker: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Muitos cards exibem cliente e responsável. joined elimina consultas
    # extras principalmente na visão de Equipe.
    client: Mapped[Client] = relationship(back_populates="projects", lazy="joined")
    analyst: Mapped[Analyst | None] = relationship(back_populates="projects", lazy="joined")
    metrics: Mapped[list["ProjectMetric"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    history: Mapped[list["ProjectHistory"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class ProjectMetric(Base):
    __tablename__ = "project_metrics"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    current_value: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=0)
    target_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    unit: Mapped[str | None] = mapped_column(String(40))
    reference_date: Mapped[date | None] = mapped_column(Date)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    project: Mapped[Project] = relationship(back_populates="metrics")


class ProjectHistory(Base):
    __tablename__ = "project_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    action: Mapped[str] = mapped_column(String(80))
    summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    project: Mapped[Project] = relationship(back_populates="history")
