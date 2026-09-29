from datetime import date, timedelta
from decimal import Decimal
from sqlalchemy import select
from app.db import Base, SessionLocal, engine
from app.models import Analyst, Client, Project, ProjectMetric

Base.metadata.create_all(engine)
db = SessionLocal()
try:
    if db.scalar(select(Project).limit(1)):
        print("Já existem projetos. Seed de demonstração ignorado.")
        raise SystemExit(0)
    analysts=[]
    for name in ["Analista 1", "Analista 2", "Analista 3", "Analista 4", "Analista 5"]:
        a=Analyst(name=name, role_title="Analista de Planejamento", active=True); db.add(a); db.flush(); analysts.append(a)
    clients=[]
    for name,segment in [("Cliente Alfa","Telecom"),("Cliente Beta","Financeiro"),("Cliente Gama","Varejo"),("Cliente Delta","Serviços")]:
        c=Client(name=name, segment=segment, active=True); db.add(c); db.flush(); clients.append(c)
    today=date.today()
    projects=[
        Project(client_id=clients[0].id,analyst_id=analysts[0].id,product="ADA",portfolio_name="Cobrança Digital",poc_start_date=today-timedelta(days=10),poc_end_date=today+timedelta(days=12),target_date=today+timedelta(days=12),stage="POC",status="Em andamento",health="Saudável",priority="Alta",progress_percent=62,potential_revenue=Decimal("85000"),objective="Validar ganho de conversão e eficiência operacional",next_step="Revisar resultado por faixa de atraso"),
        Project(client_id=clients[1].id,analyst_id=analysts[1].id,product="Locator",portfolio_name="Enriquecimento CPC",poc_start_date=today-timedelta(days=18),poc_end_date=today-timedelta(days=2),target_date=today-timedelta(days=2),stage="POC",status="Em ajuste",health="Crítico",priority="Alta",progress_percent=78,potential_revenue=Decimal("47000"),objective="Elevar localização com menor esforço humano",blocker="Aguardando nova base do cliente",next_step="Cobrar carga corrigida e retestar"),
        Project(client_id=clients[2].id,analyst_id=analysts[2].id,product="ADA",portfolio_name="Negociação IA",poc_start_date=today-timedelta(days=35),poc_end_date=today-timedelta(days=10),target_date=today-timedelta(days=10),stage="Produção",status="Implantado",health="Saudável",priority="Média",progress_percent=100,potential_revenue=Decimal("120000"),objective="Automatizar acordos com manutenção de qualidade"),
        Project(client_id=clients[3].id,analyst_id=analysts[3].id,product="Locator",portfolio_name="POC Localização",poc_start_date=today+timedelta(days=3),poc_end_date=today+timedelta(days=18),target_date=today+timedelta(days=18),stage="Homologação",status="Em andamento",health="Atenção",priority="Média",progress_percent=35,potential_revenue=Decimal("33000"),objective="Preparar ambiente e validar telefonia",next_step="Concluir homologação de campanha"),
    ]
    db.add_all(projects); db.flush()
    db.add_all([
        ProjectMetric(project_id=projects[0].id,name="Acordos/dia",current_value=129,target_value=150,unit="acordos",reference_date=today),
        ProjectMetric(project_id=projects[0].id,name="Conversão",current_value=21.3,target_value=23,unit="%",reference_date=today),
        ProjectMetric(project_id=projects[1].id,name="CPC/HC",current_value=48,target_value=55,unit="",reference_date=today),
        ProjectMetric(project_id=projects[1].id,name="Atendimento",current_value=2.83,target_value=3.2,unit="%",reference_date=today),
        ProjectMetric(project_id=projects[2].id,name="Valor recuperado",current_value=98200,target_value=90000,unit="R$",reference_date=today),
    ])
    db.commit(); print("Dados de demonstração criados.")
finally:
    db.close()
