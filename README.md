# OLOS Portfolio Command Center

Projeto independente para gestão de clientes, POCs, analistas e resultados de Locator e ADA.

## O que já vem pronto

- Tela de login e sessão autenticada
- Perfis `ADMIN`, `EDITOR` e `VIEWER`
- Cadastro de usuários de acesso
- Cadastro e edição de analistas
- Foto de perfil do analista salva no próprio banco, sem depender do disco do servidor
- Cadastro manual de clientes
- Catálogo com 157 nomes de clientes e importação em um clique
- Busca de clientes por nome
- Cadastro e atualização de projetos/POCs
- Produto Locator ou ADA
- Início/fim da POC e prazo gerencial
- Etapa, status, prioridade, saúde e progresso
- Próxima ação, bloqueio, objetivo e observações
- Indicadores flexíveis por projeto com resultado atual e meta
- Dashboard consolidado
- Fila automática de atenção
- Capacidade por analista
- Visão consolidada por cliente
- Histórico básico das alterações
- SQLite por padrão e suporte a PostgreSQL/Neon por `DATABASE_URL`

## Rodar no Windows

1. Extraia o ZIP.
2. Copie `.env.example` para `.env` e configure suas variáveis.
3. Dê dois cliques em `start_windows.bat` ou rode manualmente.
4. Abra `http://localhost:8501`.

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python -m uvicorn app.main:app --reload --port 8501
```

Linux/macOS:

```bash
./start.sh
```

## Banco

O padrão é SQLite:

```env
DATABASE_URL=sqlite:///./data/portfolio.db
```

Para Neon/PostgreSQL, use a connection string PostgreSQL em `DATABASE_URL`. O projeto converte automaticamente para o driver `psycopg`.

Na primeira inicialização o sistema cria as tabelas. Em uma base anterior, a versão atual também adiciona automaticamente o campo de foto dos analistas (`analysts.photo_data`) caso ainda não exista.

## Carteira base de clientes

A tela **Clientes** possui o botão **Importar carteira base**. Ele cadastra somente os nomes ainda inexistentes e preserva os clientes já registrados.

Também é possível importar pelo terminal:

```bash
python -m scripts.seed_clients
```

O catálogo fica em `app/client_catalog.py` e contém 157 nomes únicos. A lista em texto puro também está em `docs/clientes_nomes.txt`.

## Fotos dos analistas

Na tela **Equipe**, use **Editar** em qualquer analista para alterar:

- nome;
- e-mail;
- cargo;
- foto de perfil.

Formatos aceitos: JPG, PNG e WEBP, até 2 MB. A imagem é persistida no banco, inclusive quando o app estiver no Render.

## Dados de demonstração opcionais

```bash
python -m scripts.seed_demo
```

## Publicar no Render

O projeto inclui `Dockerfile` e `render.yaml`. Configure no Render:

- `SECRET_KEY`
- `INITIAL_ADMIN_USERNAME`
- `INITIAL_ADMIN_PASSWORD`
- `DATABASE_URL`
- `SESSION_HTTPS_ONLY=true`

Para produção, use PostgreSQL/Neon em vez do SQLite local do container.

## Subir no GitHub

O projeto já está preparado para Git. O arquivo `.env` e bancos SQLite não entram no repositório por causa do `.gitignore`.

```bash
git init
git add .
git commit -m "OLOS Portfolio Command Center"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/SEU_REPOSITORIO.git
git push -u origin main
```

**Nunca** envie o seu `.env` para o GitHub. Mantenha credenciais do Neon, `SECRET_KEY` e senhas somente nas variáveis de ambiente do computador/Render.

## Segurança

A autenticação usa PBKDF2-SHA256 com salt por usuário. Para produção:

- use uma `SECRET_KEY` forte;
- defina `SESSION_HTTPS_ONLY=true`;
- use senhas individuais fortes;
- publique atrás de HTTPS;
- mantenha `DATABASE_URL` fora do repositório.
