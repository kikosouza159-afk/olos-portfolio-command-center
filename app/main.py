from __future__ import annotations

import base64
import os
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, inspect, select, text
from sqlalchemy.orm import Session, selectinload
from starlette.middleware.sessions import SessionMiddleware

from app.auth import can_edit, get_session_user, hash_password, is_admin, verify_password
from app.client_catalog import CLIENT_CATALOG
from app.db import Base, SessionLocal, engine, get_db
from app.models import Analyst, Client, Project, ProjectHistory, ProjectMetric, User

load_dotenv()

APP_NAME = os.getenv("APP_NAME", "OLOS Portfolio Command Center")
SECRET_KEY = os.getenv("SECRET_KEY", "local-change-me")
SESSION_HTTPS_ONLY = os.getenv("SESSION_HTTPS_ONLY", "false").lower() == "true"

PRODUCTS = ["Locator", "ADA"]
POC_DAYS_DEFAULT = {"Locator": 15, "ADA": 15}
HEALTHS = ["Saudável", "Atenção", "Crítico"]
PRIORITIES = ["Alta", "Média", "Baixa"]
STAGES = ["Planejamento", "Aguardando cliente", "Desenvolvimento", "Homologação", "POC", "POC encerrada", "Implantação", "Produção", "Concluído", "Cancelado"]
STATUSES = ["Em andamento", "Em ajuste", "Pendente", "Paralisado", "Concluído", "Implantado", "Cancelado", "Sem sucesso cliente"]

app = FastAPI(title=APP_NAME)
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, https_only=SESSION_HTTPS_ONLY, same_site="lax", max_age=8 * 60 * 60)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


def money_br(value):
    try:
        n = float(value or 0)
        text = f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {text}"
    except Exception:
        return "R$ 0,00"


def number_br(value):
    try:
        n = float(value or 0)
        if abs(n) >= 1000:
            return f"{n:,.0f}".replace(",", ".")
        if n.is_integer():
            return str(int(n))
        return f"{n:.2f}".replace(".", ",")
    except Exception:
        return "0"


templates.env.filters["money"] = money_br
templates.env.filters["num"] = number_br

MAX_ANALYST_PHOTO_BYTES = 2 * 1024 * 1024
ALLOWED_ANALYST_PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp"}


def photo_data_uri(content: bytes, content_type: str) -> str:
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:{content_type};base64,{encoded}"


def ensure_schema():
    """Apply tiny backwards-compatible upgrades without a migration framework."""
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "analysts" not in tables:
        return
    analyst_columns = {column["name"] for column in inspector.get_columns("analysts")}
    if "photo_data" not in analyst_columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE analysts ADD COLUMN photo_data TEXT"))


@app.on_event("startup")
def startup():
    Base.metadata.create_all(engine)
    ensure_schema()
    db = SessionLocal()
    try:
        if not db.scalar(select(User).limit(1)):
            db.add(User(
                name=os.getenv("INITIAL_ADMIN_NAME", "Administrador"),
                email=os.getenv("INITIAL_ADMIN_EMAIL", "admin@local"),
                username=os.getenv("INITIAL_ADMIN_USERNAME", "admin"),
                password_hash=hash_password(os.getenv("INITIAL_ADMIN_PASSWORD", "admin123")),
                role="ADMIN",
                active=True,
            ))
            db.commit()
    finally:
        db.close()


def redirect_login():
    return RedirectResponse("/login", 303)


def to_date(value: str | None):
    try:
        return date.fromisoformat(value) if value else None
    except Exception:
        return None


def to_decimal(value: str | None, default="0"):
    try:
        text = str(value or default).strip()
        if "," in text:
            text = text.replace(".", "").replace(",", ".")
        return Decimal(text)
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(default)


def normalize_poc_days(value: int | str | None, product: str | None = None) -> int:
    default = POC_DAYS_DEFAULT.get(product or "", 15)
    try:
        days = int(value) if value not in (None, "") else default
    except (TypeError, ValueError):
        days = default
    return max(1, min(365, days))


def calculate_poc_end(start: date | None, days: int) -> date | None:
    if not start:
        return None
    # Dia inicial conta como dia 1. Ex.: 01/10 + 15 dias corridos = 15/10.
    return start + timedelta(days=max(1, days) - 1)


def poc_duration_days(project: Project) -> int:
    if project.poc_start_date and project.poc_end_date:
        return max(1, (project.poc_end_date - project.poc_start_date).days + 1)
    return POC_DAYS_DEFAULT.get(project.product, 15)


def lifecycle(project: Project, today: date | None = None):
    today = today or date.today()
    text = f"{project.stage} {project.status}".lower()
    if "cancel" in text or "sem sucesso" in text:
        return "Cancelado"
    if "conclu" in text:
        return "Concluído"
    if "produção" in text or "producao" in text or "implantado" in text:
        return "Implantado"
    if project.poc_start_date and today < project.poc_start_date:
        return "POC planejada"
    if project.poc_start_date and (not project.poc_end_date or today <= project.poc_end_date):
        return "Em POC"
    if project.poc_end_date and today > project.poc_end_date:
        return "POC encerrada"
    return project.stage or "Planejamento"


def deadline(project: Project, today: date | None = None):
    today = today or date.today()
    target = project.poc_end_date
    if not target:
        return {"date": None, "days": None, "state": "Sem prazo"}
    days = (target - today).days
    life = lifecycle(project, today)
    if life in {"Implantado", "Concluído", "Cancelado"}:
        state = "Finalizado"
    elif days < 0:
        state = "Atrasado"
    elif days <= 7:
        state = "Vence em breve"
    else:
        state = "No prazo"
    return {"date": target, "days": days, "state": state}


def project_payload(project: Project):
    d = deadline(project)
    life = lifecycle(project)
    guardrails = []
    if not project.analyst_id:
        guardrails.append("Defina um responsável antes da próxima revisão.")
    if not project.objective:
        guardrails.append("Registre a hipótese/objetivo que esta POC precisa provar.")
    if life in {"Em POC", "POC encerrada"} and not project.metrics:
        guardrails.append("Cadastre pelo menos um KPI de sucesso com meta.")
    if d["state"] == "Atrasado" and life not in {"Implantado", "Concluído", "Cancelado"}:
        guardrails.append("Fim da POC vencido: registre decisão, extensão ou encerramento da POC.")
    if d["state"] == "Vence em breve" and project.progress_percent < 80:
        guardrails.append("Fim da POC próximo com progresso abaixo de 80%: priorize o próximo marco.")
    if project.health == "Crítico" and not project.blocker:
        guardrails.append("Projeto crítico sem bloqueio descrito: documente a causa raiz.")
    if life == "Em POC" and not project.next_step:
        guardrails.append("Defina a próxima ação objetiva, com entrega clara para o analista.")
    if not guardrails:
        guardrails.append("Governança em dia. Mantenha indicadores e próxima ação atualizados.")
    completeness_fields = [project.analyst_id, project.poc_start_date, project.poc_end_date, project.objective, project.next_step, project.metrics]
    governance_score = round(sum(bool(x) for x in completeness_fields) / len(completeness_fields) * 100)
    return {
        "project": project,
        "lifecycle": life,
        "deadline": d,
        "attention": project.health in {"Atenção", "Crítico"} or d["state"] in {"Atrasado", "Vence em breve"} or bool(project.blocker),
        "guardrails": guardrails,
        "governance_score": governance_score,
        "poc_days": poc_duration_days(project),
    }


def base_context(user: User, db: Session):
    return {
        "user": user,
        "app_name": APP_NAME,
        "analysts": db.scalars(select(Analyst).where(Analyst.active.is_(True)).order_by(Analyst.name)).all(),
        "clients": db.scalars(select(Client).where(Client.active.is_(True)).order_by(Client.name)).all(),
        "products": PRODUCTS,
        "poc_days_default": POC_DAYS_DEFAULT,
        "healths": HEALTHS,
        "priorities": PRIORITIES,
        "stages": STAGES,
        "statuses": STATUSES,
        "can_edit": can_edit(user),
        "is_admin": is_admin(user),
    }


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: Session = Depends(get_db)):
    if get_session_user(request, db):
        return RedirectResponse("/", 303)
    return templates.TemplateResponse(request, "login.html", {"app_name": APP_NAME, "error": None})


@app.post("/login", response_class=HTMLResponse)
def login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(func.lower(User.username) == username.strip().lower(), User.active.is_(True)))
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(request, "login.html", {"app_name": APP_NAME, "error": "Usuário ou senha inválidos."}, status_code=401)
    request.session.clear()
    request.session["user_id"] = user.id
    return RedirectResponse("/", 303)


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", 303)


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, product: str = "", analyst_id: int | None = None, health: str = "", db: Session = Depends(get_db)):
    user = get_session_user(request, db)
    if not user:
        return redirect_login()
    stmt = select(Project).options(selectinload(Project.client), selectinload(Project.analyst), selectinload(Project.metrics)).where(Project.active.is_(True))
    if product:
        stmt = stmt.where(Project.product == product)
    if analyst_id:
        stmt = stmt.where(Project.analyst_id == analyst_id)
    if health:
        stmt = stmt.where(Project.health == health)
    projects = db.scalars(stmt.order_by(Project.updated_at.desc())).all()
    payloads = [project_payload(p) for p in projects]

    summary = {
        "projects": len(projects),
        "clients": len({p.client_id for p in projects}),
        "active_pocs": sum(1 for x in payloads if x["lifecycle"] == "Em POC"),
        "implanted": sum(1 for x in payloads if x["lifecycle"] == "Implantado"),
        "attention": sum(1 for x in payloads if x["attention"]),
        "delayed": sum(1 for x in payloads if x["deadline"]["state"] == "Atrasado"),
    }
    attention = [x for x in payloads if x["attention"]][:8]

    analysts = db.scalars(select(Analyst).where(Analyst.active.is_(True)).order_by(Analyst.name)).all()
    team = []
    for analyst in analysts:
        owned = [x for x in payloads if x["project"].analyst_id == analyst.id]
        team.append({
            "analyst": analyst,
            "projects": len(owned),
            "active_pocs": sum(1 for x in owned if x["lifecycle"] == "Em POC"),
            "critical": sum(1 for x in owned if x["project"].health == "Crítico"),
            "delayed": sum(1 for x in owned if x["deadline"]["state"] == "Atrasado"),
            "avg_progress": round(sum(x["project"].progress_percent for x in owned) / len(owned)) if owned else 0,
        })
    max_load = max((x["projects"] for x in team), default=1) or 1
    for x in team:
        x["load"] = round(x["projects"] / max_load * 100)

    product_counts = {name: sum(1 for p in projects if p.product == name) for name in PRODUCTS}
    health_counts = {name: sum(1 for p in projects if p.health == name) for name in HEALTHS}

    ctx = base_context(user, db)
    ctx.update({
        "summary": summary,
        "attention": attention,
        "team": team,
        "recent": payloads[:10],
        "product_counts": product_counts,
        "health_counts": health_counts,
        "filter_product": product,
        "filter_analyst_id": analyst_id,
        "filter_health": health,
        "default_password_warning": user.username == os.getenv("INITIAL_ADMIN_USERNAME", "admin") and os.getenv("INITIAL_ADMIN_PASSWORD", "admin123") == "admin123",
    })
    return templates.TemplateResponse(request, "dashboard.html", ctx)


@app.get("/projects", response_class=HTMLResponse)
def projects_page(request: Request, q: str = "", product: str = "", analyst_id: int | None = None, health: str = "", db: Session = Depends(get_db)):
    user = get_session_user(request, db)
    if not user:
        return redirect_login()
    stmt = select(Project).options(selectinload(Project.client), selectinload(Project.analyst)).where(Project.active.is_(True))
    if q:
        stmt = stmt.join(Client).where((Client.name.ilike(f"%{q}%")) | (Project.portfolio_name.ilike(f"%{q}%")))
    if product:
        stmt = stmt.where(Project.product == product)
    if analyst_id:
        stmt = stmt.where(Project.analyst_id == analyst_id)
    if health:
        stmt = stmt.where(Project.health == health)
    projects = db.scalars(stmt.order_by(Project.updated_at.desc())).all()
    ctx = base_context(user, db)
    ctx.update({"rows": [project_payload(p) for p in projects], "q": q, "filter_product": product, "filter_analyst_id": analyst_id, "filter_health": health})
    return templates.TemplateResponse(request, "projects.html", ctx)


@app.post("/projects/new")
def create_project(
    request: Request,
    client_id: int = Form(...),
    analyst_id: str = Form(""),
    product: str = Form(...),
    portfolio_name: str = Form(""),
    model: str = Form(""),
    poc_start_date: str = Form(""),
    poc_days: int = Form(15),
    stage: str = Form("Planejamento"),
    status: str = Form("Em andamento"),
    health: str = Form("Saudável"),
    priority: str = Form("Média"),
    progress_percent: int = Form(0),
    potential_revenue: str = Form("0"),
    objective: str = Form(""),
    next_step: str = Form(""),
    blocker: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    user = get_session_user(request, db)
    if not user:
        return redirect_login()
    if not can_edit(user):
        return HTMLResponse("Sem permissão", 403)
    selected_product = product if product in PRODUCTS else "Locator"
    start_date = to_date(poc_start_date)
    duration_days = normalize_poc_days(poc_days, selected_product)
    end_date = calculate_poc_end(start_date, duration_days)
    project = Project(
        client_id=client_id,
        analyst_id=int(analyst_id) if analyst_id else None,
        product=selected_product,
        portfolio_name=portfolio_name.strip() or None,
        model=model.strip() or None,
        poc_start_date=start_date,
        poc_end_date=end_date,
        target_date=end_date,
        stage=stage if stage in STAGES else "Planejamento",
        status=status if status in STATUSES else "Em andamento",
        health=health if health in HEALTHS else "Saudável",
        priority=priority if priority in PRIORITIES else "Média",
        progress_percent=max(0, min(100, progress_percent)),
        potential_revenue=to_decimal(potential_revenue),
        objective=objective.strip() or None,
        next_step=next_step.strip() or None,
        blocker=blocker.strip() or None,
        notes=notes.strip() or None,
    )
    db.add(project)
    db.flush()
    db.add(ProjectHistory(project_id=project.id, action="CREATE", summary=f"Projeto criado por {user.name}"))
    db.commit()
    return RedirectResponse(f"/projects/{project.id}", 303)


@app.get("/projects/{project_id}", response_class=HTMLResponse)
def project_detail(project_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_session_user(request, db)
    if not user:
        return redirect_login()
    project = db.scalar(select(Project).options(selectinload(Project.client), selectinload(Project.analyst), selectinload(Project.metrics), selectinload(Project.history)).where(Project.id == project_id, Project.active.is_(True)))
    if not project:
        return HTMLResponse("Projeto não encontrado", 404)
    project.history.sort(key=lambda x: x.created_at, reverse=True)
    project.metrics.sort(key=lambda x: (x.sort_order, x.name.lower()))
    ctx = base_context(user, db)
    ctx.update({"item": project_payload(project), "project": project})
    return templates.TemplateResponse(request, "project_detail.html", ctx)


@app.post("/projects/{project_id}/update")
def update_project(
    project_id: int,
    request: Request,
    analyst_id: str = Form(""),
    product: str = Form(...),
    portfolio_name: str = Form(""),
    model: str = Form(""),
    poc_start_date: str = Form(""),
    poc_days: int = Form(15),
    stage: str = Form(...),
    status: str = Form(...),
    health: str = Form(...),
    priority: str = Form(...),
    progress_percent: int = Form(0),
    potential_revenue: str = Form("0"),
    objective: str = Form(""),
    next_step: str = Form(""),
    blocker: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    user = get_session_user(request, db)
    if not user:
        return redirect_login()
    if not can_edit(user):
        return HTMLResponse("Sem permissão", 403)
    project = db.get(Project, project_id)
    if not project or not project.active:
        return HTMLResponse("Projeto não encontrado", 404)
    old_state = f"{project.stage} | {project.status} | {project.health} | {project.progress_percent}%"
    project.analyst_id = int(analyst_id) if analyst_id else None
    project.product = product if product in PRODUCTS else project.product
    project.portfolio_name = portfolio_name.strip() or None
    project.model = model.strip() or None
    project.poc_start_date = to_date(poc_start_date)
    duration_days = normalize_poc_days(poc_days, project.product)
    project.poc_end_date = calculate_poc_end(project.poc_start_date, duration_days)
    project.target_date = project.poc_end_date
    project.stage = stage if stage in STAGES else project.stage
    project.status = status if status in STATUSES else project.status
    project.health = health if health in HEALTHS else project.health
    project.priority = priority if priority in PRIORITIES else project.priority
    project.progress_percent = max(0, min(100, progress_percent))
    project.potential_revenue = to_decimal(potential_revenue)
    project.objective = objective.strip() or None
    project.next_step = next_step.strip() or None
    project.blocker = blocker.strip() or None
    project.notes = notes.strip() or None
    new_state = f"{project.stage} | {project.status} | {project.health} | {project.progress_percent}%"
    db.add(ProjectHistory(project_id=project.id, action="UPDATE", summary=f"{user.name}: {old_state} → {new_state}"))
    db.commit()
    return RedirectResponse(f"/projects/{project.id}", 303)


@app.post("/projects/{project_id}/metrics")
def add_metric(project_id: int, request: Request, name: str = Form(...), current_value: str = Form("0"), target_value: str = Form(""), unit: str = Form(""), reference_date: str = Form(""), db: Session = Depends(get_db)):
    user = get_session_user(request, db)
    if not user:
        return redirect_login()
    if not can_edit(user):
        return HTMLResponse("Sem permissão", 403)
    project = db.get(Project, project_id)
    if not project or not project.active:
        return HTMLResponse("Projeto não encontrado", 404)
    metric_name = name.strip()
    metric = db.scalar(select(ProjectMetric).where(ProjectMetric.project_id == project_id, func.lower(ProjectMetric.name) == metric_name.lower()))
    if not metric:
        metric = ProjectMetric(project_id=project_id, name=metric_name)
        db.add(metric)
    metric.current_value = to_decimal(current_value)
    metric.target_value = to_decimal(target_value) if target_value.strip() else None
    metric.unit = unit.strip() or None
    metric.reference_date = to_date(reference_date) or date.today()
    db.add(ProjectHistory(project_id=project.id, action="METRIC", summary=f"{user.name} atualizou {metric_name}"))
    db.commit()
    return RedirectResponse(f"/projects/{project.id}", 303)


@app.post("/projects/{project_id}/delete")
def delete_project(project_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_session_user(request, db)
    if not user:
        return redirect_login()
    if not is_admin(user):
        return HTMLResponse("Sem permissão", 403)
    project = db.get(Project, project_id)
    if project:
        project.active = False
        db.add(ProjectHistory(project_id=project.id, action="DELETE", summary=f"Desativado por {user.name}"))
        db.commit()
    return RedirectResponse("/projects", 303)


@app.get("/clients", response_class=HTMLResponse)
def clients_page(request: Request, q: str = "", imported: int = 0, db: Session = Depends(get_db)):
    user = get_session_user(request, db)
    if not user:
        return redirect_login()
    stmt = (
        select(Client)
        .options(selectinload(Client.projects).selectinload(Project.metrics))
        .where(Client.active.is_(True))
        .order_by(Client.name)
    )
    if q.strip():
        stmt = stmt.where(func.lower(Client.name).like(f"%{q.strip().lower()}%"))
    clients = db.scalars(stmt).all()
    cards = []
    for client in clients:
        active_projects = [p for p in client.projects if p.active]
        health_rank = {"Crítico": 0, "Atenção": 1, "Saudável": 2}
        worst = sorted((p.health for p in active_projects), key=lambda x: health_rank.get(x, 9))[0] if active_projects else "Saudável"
        metrics = []
        for p in active_projects:
            for m in p.metrics:
                metrics.append(m)
        unique = {}
        for m in sorted(metrics, key=lambda x: x.updated_at, reverse=True):
            unique.setdefault(m.name.lower(), m)
        cards.append({
            "client": client,
            "projects": active_projects,
            "health": worst,
            "products": sorted({p.product for p in active_projects}),
            "active_pocs": sum(1 for p in active_projects if lifecycle(p) == "Em POC"),
            "implanted": sum(1 for p in active_projects if lifecycle(p) == "Implantado"),
            "metrics": list(unique.values())[:4],
        })
    ctx = base_context(user, db)
    ctx.update({
        "cards": cards,
        "q": q,
        "imported": imported,
        "client_catalog_count": len(CLIENT_CATALOG),
    })
    return templates.TemplateResponse(request, "clients.html", ctx)


@app.post("/clients/new")
def create_client(request: Request, name: str = Form(...), segment: str = Form(""), db: Session = Depends(get_db)):
    user = get_session_user(request, db)
    if not user:
        return redirect_login()
    if not can_edit(user):
        return HTMLResponse("Sem permissão", 403)
    client_name = name.strip()
    existing = db.scalar(select(Client).where(func.lower(Client.name) == client_name.lower()))
    if existing:
        existing.active = True
        if segment.strip():
            existing.segment = segment.strip()
    else:
        db.add(Client(name=client_name, segment=segment.strip() or None, active=True))
    db.commit()
    return RedirectResponse("/clients", 303)


@app.post("/clients/import-catalog")
def import_client_catalog(request: Request, db: Session = Depends(get_db)):
    user = get_session_user(request, db)
    if not user:
        return redirect_login()
    if not can_edit(user):
        return HTMLResponse("Sem permissão", 403)
    existing = {name.casefold() for name in db.scalars(select(Client.name)).all()}
    added = 0
    for client_name in CLIENT_CATALOG:
        key = client_name.casefold()
        if key in existing:
            continue
        db.add(Client(name=client_name, active=True))
        existing.add(key)
        added += 1
    db.commit()
    return RedirectResponse(f"/clients?imported={added}", 303)


@app.get("/team", response_class=HTMLResponse)
def team_page(request: Request, db: Session = Depends(get_db)):
    user = get_session_user(request, db)
    if not user:
        return redirect_login()
    analysts = db.scalars(select(Analyst).options(selectinload(Analyst.projects)).where(Analyst.active.is_(True)).order_by(Analyst.name)).all()
    cards = []
    for a in analysts:
        projects = [p for p in a.projects if p.active]
        cards.append({
            "analyst": a,
            "projects": projects,
            "active_pocs": sum(1 for p in projects if lifecycle(p) == "Em POC"),
            "attention": sum(1 for p in projects if p.health in {"Atenção", "Crítico"}),
            "avg_progress": round(sum(p.progress_percent for p in projects) / len(projects)) if projects else 0,
        })
    ctx = base_context(user, db)
    ctx.update({"cards": cards, "max_photo_mb": MAX_ANALYST_PHOTO_BYTES // (1024 * 1024)})
    return templates.TemplateResponse(request, "team.html", ctx)


async def _read_analyst_photo(photo: UploadFile | None):
    if not photo or not photo.filename:
        return None, None
    content_type = (photo.content_type or "").lower()
    if content_type not in ALLOWED_ANALYST_PHOTO_TYPES:
        return None, "Formato de foto inválido. Use JPG, PNG ou WEBP."
    content = await photo.read(MAX_ANALYST_PHOTO_BYTES + 1)
    if len(content) > MAX_ANALYST_PHOTO_BYTES:
        return None, f"A foto deve ter no máximo {MAX_ANALYST_PHOTO_BYTES // (1024 * 1024)} MB."
    return photo_data_uri(content, content_type), None


@app.post("/team/new")
async def create_analyst(
    request: Request,
    name: str = Form(...),
    email: str = Form(""),
    role_title: str = Form("Analista"),
    photo: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    user = get_session_user(request, db)
    if not user:
        return redirect_login()
    if not can_edit(user):
        return HTMLResponse("Sem permissão", 403)
    analyst_name = name.strip()
    existing = db.scalar(select(Analyst).where(func.lower(Analyst.name) == analyst_name.lower()))
    photo_data, photo_error = await _read_analyst_photo(photo)
    if photo_error:
        return HTMLResponse(photo_error, 400)
    if existing:
        existing.active = True
        existing.email = email.strip() or existing.email
        existing.role_title = role_title.strip() or existing.role_title
        if photo_data:
            existing.photo_data = photo_data
    else:
        db.add(Analyst(
            name=analyst_name,
            email=email.strip() or None,
            role_title=role_title.strip() or "Analista",
            photo_data=photo_data,
            active=True,
        ))
    db.commit()
    return RedirectResponse("/team", 303)


@app.post("/team/{analyst_id}/edit")
async def edit_analyst(
    analyst_id: int,
    request: Request,
    name: str = Form(...),
    email: str = Form(""),
    role_title: str = Form("Analista"),
    remove_photo: str = Form(""),
    photo: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    user = get_session_user(request, db)
    if not user:
        return redirect_login()
    if not can_edit(user):
        return HTMLResponse("Sem permissão", 403)
    analyst = db.get(Analyst, analyst_id)
    if not analyst:
        return HTMLResponse("Analista não encontrado", 404)
    analyst_name = name.strip()
    duplicate = db.scalar(
        select(Analyst).where(
            func.lower(Analyst.name) == analyst_name.lower(),
            Analyst.id != analyst_id,
        )
    )
    if duplicate:
        return HTMLResponse("Já existe outro analista com esse nome.", 409)
    photo_data, photo_error = await _read_analyst_photo(photo)
    if photo_error:
        return HTMLResponse(photo_error, 400)
    analyst.name = analyst_name
    analyst.email = email.strip() or None
    analyst.role_title = role_title.strip() or "Analista"
    if remove_photo == "1":
        analyst.photo_data = None
    if photo_data:
        analyst.photo_data = photo_data
    db.commit()
    return RedirectResponse("/team", 303)


@app.get("/users", response_class=HTMLResponse)
def users_page(request: Request, db: Session = Depends(get_db)):
    user = get_session_user(request, db)
    if not user:
        return redirect_login()
    if not is_admin(user):
        return HTMLResponse("Sem permissão", 403)
    rows = db.scalars(select(User).order_by(User.name)).all()
    ctx = base_context(user, db)
    ctx.update({"rows": rows})
    return templates.TemplateResponse(request, "users.html", ctx)


@app.post("/users/new")
def create_user(request: Request, name: str = Form(...), email: str = Form(...), username: str = Form(...), password: str = Form(...), role: str = Form("VIEWER"), db: Session = Depends(get_db)):
    user = get_session_user(request, db)
    if not user:
        return redirect_login()
    if not is_admin(user):
        return HTMLResponse("Sem permissão", 403)
    role = role if role in {"ADMIN", "EDITOR", "VIEWER"} else "VIEWER"
    db.add(User(name=name.strip(), email=email.strip().lower(), username=username.strip(), password_hash=hash_password(password), role=role, active=True))
    db.commit()
    return RedirectResponse("/users", 303)


@app.post("/users/{user_id}/toggle")
def toggle_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_session_user(request, db)
    if not user:
        return redirect_login()
    if not is_admin(user):
        return HTMLResponse("Sem permissão", 403)
    target = db.get(User, user_id)
    if target and target.id != user.id:
        target.active = not target.active
        db.commit()
    return RedirectResponse("/users", 303)


@app.get("/health")
def healthcheck():
    return {"status": "ok", "app": APP_NAME, "time": datetime.utcnow().isoformat()}
